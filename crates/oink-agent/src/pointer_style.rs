//! User-local Windows arrow customization. Other cursor roles are never written.
//! The original registry type/bytes (including absence) are retained separately
//! from preferences, so returning to System does not invent a cursor scheme.

use std::path::Path;

use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};

use crate::config::{PointerSize, PointerStyle};

const MAX_VALUE_BYTES: usize = 16 * 1024;
const MAX_BACKUP_BYTES: usize = 192 * 1024;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ArrowValue {
    kind: u32,
    bytes: Vec<u8>,
}

impl ArrowValue {
    fn validate(&self) -> Result<()> {
        ensure!(matches!(self.kind, 1 | 2), "Arrow must be REG_SZ or REG_EXPAND_SZ");
        ensure!(self.bytes.len() <= MAX_VALUE_BYTES, "Arrow registry value is too large");
        Ok(())
    }

    fn builtin(file: &str) -> Self {
        Self {
            kind: 2, // REG_EXPAND_SZ; Windows resolves its own system directory.
            bytes: format!("%SystemRoot%\\Cursors\\{file}")
                .encode_utf16()
                .chain(std::iter::once(0))
                .flat_map(u16::to_le_bytes)
                .collect(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Backup {
    schema: u32,
    original: Option<ArrowValue>,
    last_applied: ArrowValue,
}

impl Backup {
    fn validate(&self) -> Result<()> {
        ensure!(self.schema == 1, "Unknown pointer backup schema");
        if let Some(original) = &self.original {
            original.validate()?;
        }
        self.last_applied.validate()
    }
}

fn cursor_file(style: PointerStyle, size: PointerSize) -> Option<&'static str> {
    use PointerSize::*;
    use PointerStyle::*;
    Some(match (style, size) {
        (System, _) => return None,
        (White, Normal) => "aero_arrow.cur",
        (White, Large) => "aero_arrow_l.cur",
        (White, ExtraLarge) => "aero_arrow_xl.cur",
        (Black, Normal) => "arrow_r.cur",
        (Black, Large) => "arrow_rm.cur",
        (Black, ExtraLarge) => "arrow_rl.cur",
        (Inverted, Normal) => "arrow_i.cur",
        (Inverted, Large) => "arrow_im.cur",
        (Inverted, ExtraLarge) => "arrow_il.cur",
    })
}

trait Environment {
    fn read_arrow(&mut self) -> Result<Option<ArrowValue>>;
    fn write_arrow(&mut self, value: Option<&ArrowValue>) -> Result<()>;
    fn reload(&mut self) -> Result<()>;
    fn read_backup(&mut self) -> Result<Option<Backup>>;
    fn write_backup(&mut self, value: Option<&Backup>) -> Result<()>;
}

/// Registry and backup changes are one logical transaction. Keep a valid backup
/// until a System restore has reloaded successfully. All tests use a fake OS.
fn transact_with_commit<T>(
    env: &mut impl Environment,
    desired: Option<ArrowValue>,
    commit: impl FnOnce() -> Result<T>,
) -> Result<T> {
    let current = env.read_arrow()?;
    if let Some(current) = &current {
        current.validate()?;
    }
    let previous = env.read_backup()?;
    if let Some(previous) = &previous {
        previous.validate()?;
    }
    let (target, next) = match desired {
        Some(value) => {
            value.validate()?;
            // An external Control Panel change becomes the new restore point.
            let original = previous
                .as_ref()
                .filter(|backup| current.as_ref() == Some(&backup.last_applied))
                .map_or_else(|| current.clone(), |backup| backup.original.clone());
            let backup = Backup {
                schema: 1,
                original,
                last_applied: value.clone(),
            };
            (Some(value), Some(backup))
        }
        None => match &previous {
            Some(backup) if current.as_ref() == Some(&backup.last_applied) => (backup.original.clone(), None),
            // Do not overwrite a cursor selected outside this app.
            _ => (current.clone(), None),
        },
    };
    if target == current && next == previous {
        return commit();
    }
    let mut registry_attempted = false;
    let result: Result<T> = (|| {
        if next.is_some() && next != previous {
            env.write_backup(next.as_ref())
                .context("Save original pointer before changing it")?;
        }
        if target != current {
            ensure!(
                env.read_arrow()? == current,
                "Windows arrow changed while applying the setting"
            );
            registry_attempted = true;
            env.write_arrow(target.as_ref())
                .context("Write Windows arrow setting")?;
            env.reload().context("Reload Windows cursors")?;
        }
        if next.is_none() && next != previous {
            env.write_backup(None)
                .context("Finish restoring the original pointer")?;
        }
        commit()
    })();
    match result {
        Ok(value) => Ok(value),
        Err(error) => {
            let mut rollback_errors = Vec::new();
            if registry_attempted {
                let rollback: Result<()> = (|| {
                    let observed = env.read_arrow()?;
                    if observed == target {
                        env.write_arrow(current.as_ref())?;
                        env.reload()?;
                    } else if observed != current {
                        bail!("Windows arrow changed externally; the external choice was preserved");
                    }
                    Ok(())
                })();
                if let Err(error) = rollback {
                    rollback_errors.push(format!("arrow: {error:#}"));
                }
            }
            if let Err(error) = env.write_backup(previous.as_ref()) {
                rollback_errors.push(format!("backup: {error:#}"));
            }
            if !rollback_errors.is_empty() {
                bail!("{error:#}; pointer rollback failed: {}", rollback_errors.join("; "));
            }
            Err(error)
        }
    }
}

/// Called only by the local settings owner. Unit tests must never change the
/// developer's Windows cursor; they exercise `transact` using a fake environment.
pub(crate) fn apply(data_dir: &Path, style: PointerStyle, size: PointerSize) -> Result<()> {
    apply_and_commit(data_dir, style, size, || Ok(()))
}

/// Hold the native transaction through configuration persistence. If saving the
/// preferences fails, restore the exact pre-call arrow and backup, even if the
/// Windows setting had been changed externally since the last saved preferences.
pub(crate) fn apply_and_commit<T>(
    data_dir: &Path,
    style: PointerStyle,
    size: PointerSize,
    commit: impl FnOnce() -> Result<T>,
) -> Result<T> {
    #[cfg(test)]
    {
        let _ = (data_dir, style, size);
        commit()
    }
    #[cfg(all(windows, not(test)))]
    {
        static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
        let _guard = LOCK
            .lock()
            .map_err(|_| anyhow::anyhow!("Pointer settings lock poisoned"))?;
        let desired = cursor_file(style, size).map(platform::validated_value).transpose()?;
        transact_with_commit(&mut platform::Windows::new(data_dir), desired, commit)
    }
    #[cfg(all(not(windows), not(test)))]
    {
        let _ = (data_dir, size);
        ensure!(
            style == PointerStyle::System,
            "Arrow customization is only available on Windows"
        );
        commit()
    }
}

#[cfg(windows)]
#[cfg_attr(test, allow(dead_code))]
mod platform {
    use super::*;
    use std::{io::Read, os::windows::ffi::OsStrExt, path::PathBuf};
    use windows::{
        Win32::{
            Foundation::{ERROR_FILE_NOT_FOUND, ERROR_MORE_DATA},
            System::{
                Registry::{
                    HKEY, HKEY_CURRENT_USER, KEY_QUERY_VALUE, KEY_SET_VALUE, REG_SAM_FLAGS, REG_VALUE_TYPE,
                    RegCloseKey, RegDeleteValueW, RegOpenKeyExW, RegQueryValueExW, RegSetValueExW,
                },
                SystemInformation::GetWindowsDirectoryW,
            },
            UI::WindowsAndMessaging::{
                DestroyCursor, HCURSOR, IMAGE_CURSOR, LR_LOADFROMFILE, LoadImageW, SPI_SETCURSORS,
                SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS, SystemParametersInfoW,
            },
        },
        core::{PCWSTR, w},
    };

    #[derive(Debug)]
    struct Key(HKEY);
    impl Drop for Key {
        fn drop(&mut self) {
            // SAFETY: this key was opened by RegOpenKeyExW and is owned here.
            let _ = unsafe { RegCloseKey(self.0) };
        }
    }
    fn key(access: REG_SAM_FLAGS) -> Result<Option<Key>> {
        let mut handle = HKEY::default();
        // SAFETY: fixed HKCU subkey and valid writable output handle.
        let status = unsafe {
            RegOpenKeyExW(
                HKEY_CURRENT_USER,
                w!("Control Panel\\Cursors"),
                None,
                access,
                &mut handle,
            )
        };
        if status == ERROR_FILE_NOT_FOUND {
            return Ok(None);
        }
        status.ok().context("Open current user's cursor settings")?;
        Ok(Some(Key(handle)))
    }

    pub(super) fn validated_value(file: &str) -> Result<ArrowValue> {
        let mut buffer = vec![0u16; 32768];
        // SAFETY: Windows writes at most the length of this owned UTF-16 buffer.
        let len = unsafe { GetWindowsDirectoryW(Some(&mut buffer)) } as usize;
        ensure!(len > 0 && len < buffer.len(), "Cannot locate the Windows directory");
        let directory = String::from_utf16(&buffer[..len]).context("Invalid Windows directory")?;
        let path = PathBuf::from(directory).join("Cursors").join(file);
        ensure!(path.is_file(), "Built-in Windows cursor is missing: {}", path.display());
        let wide: Vec<u16> = path.as_os_str().encode_wide().chain(std::iter::once(0)).collect();
        // SAFETY: the filename is NUL-terminated and lives through the call.
        // Without LR_SHARED this creates a private cursor owned by this function.
        let image = unsafe { LoadImageW(None, PCWSTR(wide.as_ptr()), IMAGE_CURSOR, 0, 0, LR_LOADFROMFILE) }
            .context("Validate built-in Windows cursor")?;
        // SAFETY: IMAGE_CURSOR without LR_SHARED returns a private cursor handle.
        unsafe { DestroyCursor(HCURSOR(image.0)) }.context("Release validated Windows cursor")?;
        Ok(ArrowValue::builtin(file))
    }

    #[derive(Debug)]
    pub(super) struct Windows {
        backup: PathBuf,
    }
    impl Windows {
        pub(super) fn new(data_dir: &Path) -> Self {
            Self {
                backup: data_dir.join("pointer-style-backup.json"),
            }
        }
    }
    impl Environment for Windows {
        fn read_arrow(&mut self) -> Result<Option<ArrowValue>> {
            let Some(key) = key(KEY_QUERY_VALUE)? else {
                return Ok(None);
            };
            let mut kind = REG_VALUE_TYPE::default();
            let mut bytes = vec![0u8; MAX_VALUE_BYTES];
            let mut length = bytes.len() as u32;
            // SAFETY: output pointers match the allocated buffer and length.
            // RegQueryValueExW deliberately preserves raw bytes and REG_EXPAND_SZ,
            // unlike RegGetValueW's automatic expansion/termination behavior.
            let status = unsafe {
                RegQueryValueExW(
                    key.0,
                    w!("Arrow"),
                    None,
                    Some(&mut kind),
                    Some(bytes.as_mut_ptr()),
                    Some(&mut length),
                )
            };
            if status == ERROR_FILE_NOT_FOUND {
                return Ok(None);
            }
            ensure!(
                status != ERROR_MORE_DATA && length as usize <= MAX_VALUE_BYTES,
                "Arrow registry value is too large"
            );
            status.ok().context("Read current Windows arrow")?;
            bytes.truncate(length as usize);
            let value = ArrowValue { kind: kind.0, bytes };
            value.validate()?;
            Ok(Some(value))
        }

        fn write_arrow(&mut self, value: Option<&ArrowValue>) -> Result<()> {
            let key = key(KEY_SET_VALUE)?.context("The user's Windows cursor key is missing")?;
            let status = if let Some(value) = value {
                value.validate()?;
                // SAFETY: fixed value name and validated bounded raw registry data.
                unsafe { RegSetValueExW(key.0, w!("Arrow"), None, REG_VALUE_TYPE(value.kind), Some(&value.bytes)) }
            } else {
                // SAFETY: delete only this user's Arrow value, preserving all other roles.
                unsafe { RegDeleteValueW(key.0, w!("Arrow")) }
            };
            if value.is_none() && status == ERROR_FILE_NOT_FOUND {
                return Ok(());
            }
            status.ok().context("Update Windows arrow registry value")
        }

        fn reload(&mut self) -> Result<()> {
            // SAFETY: SPI_SETCURSORS takes no pointer and reloads the user's saved
            // cursor scheme; only Arrow was changed above, so other roles stay intact.
            unsafe { SystemParametersInfoW(SPI_SETCURSORS, 0, None, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0)) }
                .context("Apply saved Windows cursor settings")
        }

        fn read_backup(&mut self) -> Result<Option<Backup>> {
            let file = match std::fs::File::open(&self.backup) {
                Ok(file) => file,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
                Err(error) => return Err(error.into()),
            };
            let mut bytes = Vec::new();
            file.take(MAX_BACKUP_BYTES as u64 + 1).read_to_end(&mut bytes)?;
            ensure!(bytes.len() <= MAX_BACKUP_BYTES, "Pointer backup is too large");
            let backup: Option<Backup> = serde_json::from_slice(&bytes).context("Read original pointer backup")?;
            if let Some(backup) = &backup {
                backup.validate()?;
            }
            Ok(backup)
        }

        fn write_backup(&mut self, value: Option<&Backup>) -> Result<()> {
            if let Some(value) = value {
                value.validate()?;
            }
            // JSON null is an atomic tombstone; do not remove a backup between
            // registry operations or replace the original with an invented default.
            let bytes = serde_json::to_vec(&value)?;
            ensure!(bytes.len() <= MAX_BACKUP_BYTES, "Pointer backup is too large");
            oink_foundation::storage::atomic_write(&self.backup, &bytes).context("Persist original pointer backup")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn transact(env: &mut impl Environment, desired: Option<ArrowValue>) -> Result<()> {
        transact_with_commit(env, desired, || Ok(()))
    }

    #[derive(Debug, Default)]
    struct Fake {
        arrow: Option<ArrowValue>,
        backup: Option<Backup>,
        writes: usize,
        reloads: usize,
        fail_write: bool,
        fail_reload: bool,
        fail_backup: bool,
        fail_clear: bool,
    }
    impl Environment for Fake {
        fn read_arrow(&mut self) -> Result<Option<ArrowValue>> {
            Ok(self.arrow.clone())
        }
        fn write_arrow(&mut self, value: Option<&ArrowValue>) -> Result<()> {
            self.writes += 1;
            if std::mem::take(&mut self.fail_write) {
                bail!("simulated registry failure");
            }
            self.arrow = value.cloned();
            Ok(())
        }
        fn reload(&mut self) -> Result<()> {
            self.reloads += 1;
            if std::mem::take(&mut self.fail_reload) {
                bail!("simulated reload failure");
            }
            Ok(())
        }
        fn read_backup(&mut self) -> Result<Option<Backup>> {
            Ok(self.backup.clone())
        }
        fn write_backup(&mut self, value: Option<&Backup>) -> Result<()> {
            if std::mem::take(&mut self.fail_backup) || (value.is_none() && std::mem::take(&mut self.fail_clear)) {
                bail!("simulated backup failure");
            }
            self.backup = value.cloned();
            Ok(())
        }
    }

    fn original() -> ArrowValue {
        ArrowValue {
            kind: 1,
            bytes: vec![0x41, 0, 0, 0],
        }
    }
    fn black() -> ArrowValue {
        ArrowValue::builtin("arrow_r.cur")
    }
    fn white() -> ArrowValue {
        ArrowValue::builtin("aero_arrow.cur")
    }

    #[test]
    fn restores_exact_original_type_bytes_and_absence() {
        for original in [
            None,
            Some(original()),
            Some(ArrowValue {
                kind: 2,
                bytes: vec![0, 0],
            }),
        ] {
            let mut env = Fake {
                arrow: original.clone(),
                ..Default::default()
            };
            transact(&mut env, Some(black())).unwrap();
            assert_eq!(env.backup.as_ref().unwrap().original, original);
            transact(&mut env, Some(white())).unwrap();
            assert_eq!(env.backup.as_ref().unwrap().original, original);
            transact(&mut env, None).unwrap();
            assert_eq!(env.arrow, original);
            assert_eq!(env.backup, None);
        }
    }

    #[test]
    fn system_does_not_clobber_external_changes_and_new_style_recaptures_them() {
        let mut env = Fake {
            arrow: Some(original()),
            ..Default::default()
        };
        transact(&mut env, Some(black())).unwrap();
        let external = ArrowValue {
            kind: 1,
            bytes: vec![0x42, 0, 0, 0],
        };
        env.arrow = Some(external.clone());
        transact(&mut env, Some(white())).unwrap();
        assert_eq!(env.backup.as_ref().unwrap().original, Some(external.clone()));
        env.arrow = Some(original());
        let writes = env.writes;
        transact(&mut env, None).unwrap();
        assert_eq!(env.arrow, Some(original()));
        assert_eq!(env.writes, writes);
        assert_eq!(env.backup, None);
    }

    #[test]
    fn failed_registry_write_reload_or_backup_leaves_previous_state() {
        for failure in 0..3 {
            let mut env = Fake {
                arrow: Some(original()),
                ..Default::default()
            };
            transact(&mut env, Some(black())).unwrap();
            let previous = env.backup.clone();
            env.fail_write = failure == 0;
            env.fail_reload = failure == 1;
            env.fail_backup = failure == 2;
            assert!(transact(&mut env, Some(white())).is_err());
            assert_eq!(env.arrow, Some(black()));
            assert_eq!(env.backup, previous);
        }
    }

    #[test]
    fn failed_final_backup_clear_rolls_back_a_system_restore() {
        let mut env = Fake {
            arrow: Some(original()),
            ..Default::default()
        };
        transact(&mut env, Some(black())).unwrap();
        let previous = env.backup.clone();
        env.fail_clear = true;
        assert!(transact(&mut env, None).is_err());
        assert_eq!(env.arrow, Some(black()));
        assert_eq!(env.backup, previous);
    }

    #[test]
    fn config_failure_restores_external_arrow_and_previous_backup_exactly() {
        let mut env = Fake {
            arrow: Some(original()),
            ..Default::default()
        };
        transact(&mut env, Some(black())).unwrap();
        let previous = env.backup.clone();
        let external = ArrowValue {
            kind: 1,
            bytes: vec![0x43, 0, 0, 0],
        };
        env.arrow = Some(external.clone());
        let result: Result<()> = transact_with_commit(&mut env, Some(white()), || bail!("config save failed"));
        assert!(result.is_err());
        assert_eq!(env.arrow, Some(external));
        assert_eq!(env.backup, previous);
    }

    #[test]
    fn config_failure_after_system_restore_recovers_custom_arrow_and_backup() {
        let mut env = Fake {
            arrow: None,
            ..Default::default()
        };
        transact(&mut env, Some(black())).unwrap();
        let previous = env.backup.clone();
        let result: Result<()> = transact_with_commit(&mut env, None, || bail!("config save failed"));
        assert!(result.is_err());
        assert_eq!(env.arrow, Some(black()));
        assert_eq!(env.backup, previous);
    }

    #[test]
    fn commit_runs_once_even_when_native_values_already_match() {
        let mut env = Fake {
            arrow: Some(original()),
            ..Default::default()
        };
        let mut commits = 0;
        let value = transact_with_commit(&mut env, None, || {
            commits += 1;
            Ok(42)
        })
        .unwrap();
        assert_eq!((value, commits, env.writes), (42, 1, 0));
        env.fail_backup = true;
        let result = transact_with_commit(&mut env, Some(black()), || {
            commits += 1;
            Ok(())
        });
        assert!(result.is_err());
        assert_eq!(commits, 1, "never commit config after a native transaction failure");
    }

    #[test]
    fn invalid_backups_and_oversized_values_never_change_windows() {
        let mut env = Fake {
            arrow: Some(original()),
            ..Default::default()
        };
        env.backup = Some(Backup {
            schema: 99,
            original: None,
            last_applied: black(),
        });
        assert!(transact(&mut env, Some(white())).is_err());
        env.backup = None;
        env.arrow = Some(ArrowValue {
            kind: 1,
            bytes: vec![0; MAX_VALUE_BYTES + 1],
        });
        assert!(transact(&mut env, Some(white())).is_err());
        env.arrow = Some(ArrowValue {
            kind: 4,
            bytes: vec![0; 4],
        });
        assert!(transact(&mut env, Some(white())).is_err());
        assert_eq!(env.writes, 0);
        assert_eq!(env.reloads, 0);
    }

    #[test]
    fn repeated_apply_and_unmodified_system_are_noops() {
        let mut env = Fake {
            arrow: Some(original()),
            ..Default::default()
        };
        transact(&mut env, None).unwrap();
        assert_eq!(env.writes, 0);
        transact(&mut env, Some(black())).unwrap();
        let (writes, reloads) = (env.writes, env.reloads);
        transact(&mut env, Some(black())).unwrap();
        assert_eq!((env.writes, env.reloads), (writes, reloads));
    }

    #[test]
    fn choices_map_only_to_known_builtin_arrow_files() {
        assert_eq!(cursor_file(PointerStyle::System, PointerSize::ExtraLarge), None);
        assert_eq!(
            cursor_file(PointerStyle::White, PointerSize::Large),
            Some("aero_arrow_l.cur")
        );
        assert_eq!(
            cursor_file(PointerStyle::Black, PointerSize::Large),
            Some("arrow_rm.cur")
        );
        assert_eq!(
            cursor_file(PointerStyle::Inverted, PointerSize::ExtraLarge),
            Some("arrow_il.cur")
        );
    }
}
