//! Preserve the old personal patch's behavior once, in its user's local store.
use super::AgentConfig;
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Deserialize)]
struct Marker {
    schema: u64,
    patch_id: String,
    user_data_path: PathBuf,
}

impl AgentConfig {
    fn has_explicit_trail_mode(&self) -> bool {
        self.envelope
            .get("local")
            .and_then(|local| local.get("routing"))
            .is_some_and(|routing| !routing.is_object() || routing.get("cursor_trail_always").is_some())
    }

    #[cfg(windows)]
    pub(crate) fn migrate_installed_legacy_trail(&mut self) -> anyhow::Result<bool> {
        if self.has_explicit_trail_mode() {
            return Ok(false);
        }
        let marker = match oink_winsvc::backend::legacy_trail_marker() {
            Ok(marker) => marker,
            Err(error) => {
                // An unreadable/untrusted optional marker cannot block ordinary
                // startup or grant access to the old private backup directory.
                tracing::warn!(kind = ?error.kind(), "legacy pointer trail marker unavailable");
                return Ok(false);
            }
        };
        self.migrate_legacy_trail(marker.as_deref())
    }

    fn migrate_legacy_trail(&mut self, marker: Option<&[u8]>) -> anyhow::Result<bool> {
        // Retained JSON distinguishes an explicit false from the default. It
        // also prevents malformed explicit choices from being reinterpreted.
        if self.has_explicit_trail_mode() {
            return Ok(false);
        }
        let Some(marker) = marker else { return Ok(false) };
        let Ok(marker) = oink_update::feed::strict_json::<Marker>(marker) else {
            return Ok(false);
        };
        if marker.schema != 1 || !marker.patch_id.starts_with("movement-trail-0.3.4-") {
            return Ok(false);
        }
        let (Ok(marked_dir), Ok(data_dir)) = (marker.user_data_path.canonicalize(), self.data_dir.canonicalize())
        else {
            return Ok(false);
        };
        if marked_dir != data_dir {
            return Ok(false);
        }
        // This atomic local edit preserves owner CBOR/unknown fields and records
        // an explicit choice. A later explicit false survives the same marker.
        self.update_local(
            &serde_json::json!({"routing":{"cursor_trail_always":true}}),
            |settings| {
                settings.routing.cursor_trail_always = true;
            },
        )?;
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn stored(config: &AgentConfig) -> Value {
        serde_json::from_slice(&std::fs::read(config.settings_path()).unwrap()).unwrap()
    }

    fn fixture(local: Option<Value>) -> (tempfile::TempDir, AgentConfig, Vec<u8>, Value) {
        let dir = tempfile::tempdir().unwrap();
        let mut config = AgentConfig::load_from(dir.path()).unwrap();
        config.save().unwrap();
        let mut raw = stored(&config);
        if let Some(local) = local {
            raw["local"] = local;
        } else {
            raw.as_object_mut().unwrap().remove("local");
        }
        raw["future_envelope"] = json!({"preserved":[1,2,3]});
        std::fs::write(config.settings_path(), serde_json::to_vec(&raw).unwrap()).unwrap();
        let marker = serde_json::to_vec(&json!({
            "schema":1,
            "patch_id":"movement-trail-0.3.4-fixture",
            "user_data_path":dir.path(),
            "future_marker_field":"ignored"
        }))
        .unwrap();
        let config = AgentConfig::load_from(dir.path()).unwrap();
        (dir, config, marker, raw)
    }

    #[test]
    fn sparse_legacy_profiles_migrate_without_changing_owner_or_unrelated_settings() {
        for local in [
            None,
            Some(json!({})),
            Some(json!({"confirm_quit":false,"future_local":17})),
            Some(json!({"routing":{"forward_injected_input":false,"future_routing":23}})),
        ] {
            let (_dir, mut config, marker, before) = fixture(local);
            let owner = config.owner().clone();
            assert!(config.migrate_legacy_trail(Some(&marker)).unwrap());
            assert!(config.settings.routing.cursor_trail_always);
            assert_eq!(*config.owner(), owner);
            let mut expected = before;
            expected["local"]["routing"]["cursor_trail_always"] = json!(true);
            assert_eq!(stored(&config), expected);
            let mut restarted = AgentConfig::load_from(&config.data_dir).unwrap();
            assert!(restarted.settings.routing.cursor_trail_always);
            assert!(!restarted.migrate_legacy_trail(Some(&marker)).unwrap());
        }
    }

    #[test]
    fn explicit_mode_and_later_circle_choice_survive_persistent_marker_and_restart() {
        for explicit in [json!(false), json!(true), json!("unrecognized")] {
            let (_dir, mut config, marker, before) = fixture(Some(json!({"routing":{"cursor_trail_always":explicit}})));
            assert!(!config.migrate_legacy_trail(Some(&marker)).unwrap());
            assert_eq!(stored(&config), before);
        }
        let (_dir, mut config, marker, _) = fixture(Some(json!({})));
        assert!(config.migrate_legacy_trail(Some(&marker)).unwrap());
        config
            .update_local(&json!({"routing":{"cursor_trail_always":false}}), |s| {
                s.routing.cursor_trail_always = false
            })
            .unwrap();
        config.update(|s| s.confirm_quit = false).unwrap();
        let mut restarted = AgentConfig::load_from(&config.data_dir).unwrap();
        assert!(!restarted.migrate_legacy_trail(Some(&marker)).unwrap());
        assert!(!restarted.settings.routing.cursor_trail_always);
        assert_eq!(stored(&restarted)["local"]["routing"]["cursor_trail_always"], false);
    }

    #[test]
    fn absent_invalid_unrelated_or_other_user_marker_never_enables_mode() {
        let (_dir, mut config, marker, before) = fixture(Some(json!({})));
        assert!(!config.migrate_legacy_trail(None).unwrap());
        assert!(!config.migrate_legacy_trail(Some(b"{invalid")).unwrap());
        let other_user = tempfile::tempdir().unwrap();
        for (key, value) in [
            ("schema", json!(2)),
            ("patch_id", json!("other-patch")),
            ("user_data_path", json!(other_user.path())),
        ] {
            let mut other: Value = serde_json::from_slice(&marker).unwrap();
            other[key] = value;
            assert!(
                !config
                    .migrate_legacy_trail(Some(&serde_json::to_vec(&other).unwrap()))
                    .unwrap()
            );
        }
        assert!(!config.settings.routing.cursor_trail_always);
        assert_eq!(stored(&config), before);
        let (_dir, mut malformed, marker, before) = fixture(Some(json!({"routing":"unknown"})));
        assert!(!malformed.migrate_legacy_trail(Some(&marker)).unwrap());
        assert_eq!(stored(&malformed), before);
    }

    #[test]
    fn migration_save_failure_keeps_effective_and_retained_configuration_unchanged() {
        let (_dir, mut config, marker, _) = fixture(Some(json!({})));
        let before = config.clone();
        std::fs::remove_file(config.settings_path()).unwrap();
        std::fs::create_dir(config.settings_path()).unwrap();
        assert!(config.migrate_legacy_trail(Some(&marker)).is_err());
        assert_eq!(config.settings, before.settings);
        assert_eq!(config.envelope, before.envelope);
        assert_eq!(config.owner(), before.owner());
        std::fs::remove_dir(config.settings_path()).unwrap();
        assert!(config.migrate_legacy_trail(Some(&marker)).unwrap());
    }

    #[test]
    fn explicitly_malformed_local_object_is_not_repaired_by_loading() {
        let (_dir, config, _, mut raw) = fixture(Some(json!({})));
        for invalid in [Value::Null, json!([]), json!(false)] {
            raw["local"] = invalid;
            let bytes = serde_json::to_vec(&raw).unwrap();
            std::fs::write(config.settings_path(), &bytes).unwrap();
            assert!(AgentConfig::load_from(&config.data_dir).is_err());
            assert_eq!(std::fs::read(config.settings_path()).unwrap(), bytes);
        }
    }
}
