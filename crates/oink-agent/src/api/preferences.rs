//! Local appearance and process preferences. Owner options are edited separately.
use crate::config::{LogLevel, LogMaxMb, PointerSize, PointerStyle, ThemeAccent, ThemeColor, ThemeMode, UiLanguage};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UiPreferences {
    pub ui_language: UiLanguage,
    #[serde(default)]
    pub notification_level: super::NotificationSetting,
    pub theme_mode: ThemeMode,
    pub theme_accent: ThemeAccent,
    /// None follows the theme accent, retaining the legacy appearance.
    #[serde(default)]
    pub trail_color: Option<ThemeColor>,
    #[serde(default)]
    pub pointer_style: PointerStyle,
    #[serde(default)]
    pub pointer_size: PointerSize,
    pub show_status_icon: bool,
    pub confirm_quit: bool,
    pub paste_as_file: bool,
    pub log_level: LogLevel,
    pub log_max_mb: LogMaxMb,
}
impl From<&crate::config::Settings> for UiPreferences {
    fn from(settings: &crate::config::Settings) -> Self {
        Self {
            ui_language: settings.ui_language,
            notification_level: settings.notification_level,
            theme_mode: settings.theme_mode,
            theme_accent: settings.theme_accent.clone(),
            trail_color: settings.trail_color.clone(),
            pointer_style: settings.pointer_style,
            pointer_size: settings.pointer_size,
            show_status_icon: settings.show_status_icon,
            confirm_quit: settings.confirm_quit,
            paste_as_file: settings.paste_as_file,
            log_level: settings.log_level,
            log_max_mb: settings.log_max_mb,
        }
    }
}
impl UiPreferences {
    pub(crate) fn apply(&self, settings: &mut crate::config::Settings) {
        settings.ui_language = self.ui_language;
        settings.notification_level = self.notification_level;
        settings.theme_mode = self.theme_mode;
        settings.theme_accent = self.theme_accent.clone();
        settings.trail_color = self.trail_color.clone();
        settings.pointer_style = self.pointer_style;
        settings.pointer_size = self.pointer_size;
        settings.show_status_icon = self.show_status_icon;
        settings.confirm_quit = self.confirm_quit;
        settings.paste_as_file = self.paste_as_file;
        settings.log_level = self.log_level;
        settings.log_max_mb = self.log_max_mb;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::PreferencePatch;
    use serde_json::json;

    #[test]
    fn cursor_appearance_defaults_preserve_legacy_preferences() {
        let current = UiPreferences::from(&crate::config::Settings::default());
        let mut old = serde_json::to_value(&current).unwrap();
        for field in ["trail_color", "pointer_style", "pointer_size"] {
            old.as_object_mut().unwrap().remove(field);
        }
        let restored: UiPreferences = serde_json::from_value(old).unwrap();
        assert_eq!(restored.trail_color, None);
        assert_eq!(restored.pointer_style, PointerStyle::System);
        assert_eq!(restored.pointer_size, PointerSize::Normal);
    }

    #[test]
    fn cursor_appearance_partial_edits_validate_and_preserve_siblings() {
        let initial = UiPreferences::from(&crate::config::Settings::default());
        let patch: PreferencePatch<UiPreferences> = serde_json::from_value(json!({
            "trail_color":"#12aBcD", "pointer_style":"inverted", "pointer_size":"extra_large"
        }))
        .unwrap();
        let current = patch.apply(&initial).unwrap();
        assert_eq!(current.trail_color.as_ref().unwrap().as_str(), "#12ABCD");
        assert_eq!(current.pointer_style, PointerStyle::Inverted);
        assert_eq!(current.pointer_size, PointerSize::ExtraLarge);
        assert_eq!(current.theme_accent, initial.theme_accent);
        let reset_color: PreferencePatch<UiPreferences> = serde_json::from_value(json!({"trail_color":null})).unwrap();
        let restored = reset_color.apply(&current).unwrap();
        assert_eq!(restored.trail_color, None);
        assert_eq!(restored.pointer_style, current.pointer_style);
        assert_eq!(restored.pointer_size, current.pointer_size);
        for value in [
            json!({"trail_color":"#12345678"}),
            json!({"trail_color":"red"}),
            json!({"pointer_style":"custom"}),
            json!({"pointer_size":"huge"}),
            json!({"pointer_style":null}),
        ] {
            let invalid: PreferencePatch<UiPreferences> = serde_json::from_value(value).unwrap();
            assert!(invalid.apply(&current).is_err());
        }
    }
}
