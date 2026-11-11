import { useEffect, useRef, useState } from 'react';
import { Button, ColorSwatches, Select, toast } from 'oink-ui';
import { tr } from '../i18n';
import { ACCENT_SWATCHES, DEFAULT_ACCENT } from './appearance';
import type { LocalPreferences } from './model';

type PointerStyle = 'system' | 'white' | 'black' | 'inverted';
type PointerSize = 'normal' | 'large' | 'extra_large';
type SaveAppearance = (patch: Partial<LocalPreferences>) => Promise<void>;

/** Old profiles and unavailable/invalid snapshots keep the system appearance. */
export function readPointerAppearance(local: Partial<LocalPreferences> | null | undefined) {
    const color = local?.trail_color;
    const style = local?.pointer_style;
    const size = local?.pointer_size;
    return {
        color: typeof color === 'string' && /^#[0-9a-f]{6}$/i.test(color) ? color.toUpperCase() : null,
        style: (['white', 'black', 'inverted'].includes(style ?? '') ? style : 'system') as PointerStyle,
        size: (['large', 'extra_large'].includes(size ?? '') ? size : 'normal') as PointerSize,
    };
}

function useAppearanceSave(saveLocal: SaveAppearance, label: string) {
    const [saving, setSaving] = useState(false);
    const busy = useRef(false);
    const save = async (patch: Partial<LocalPreferences>) => {
        if (busy.current) return;
        busy.current = true;
        setSaving(true);
        try {
            await saveLocal(patch);
        } catch {
            toast.danger({ title: tr('无法更改「{0}」', label), description: tr('不可用') });
        } finally {
            busy.current = false;
            setSaving(false);
        }
    };
    return { saving, save };
}

interface AppearanceControlProps {
    local: LocalPreferences | null;
    saveLocal: SaveAppearance;
    label: string;
    disabled?: boolean;
}

export function TrailColorControl({ local, saveLocal, label, disabled = false }: AppearanceControlProps) {
    const { color } = readPointerAppearance(local);
    const [draft, setDraft] = useState(color ?? DEFAULT_ACCENT.color);
    useEffect(() => { setDraft(color ?? DEFAULT_ACCENT.color); }, [color]);
    const { saving, save } = useAppearanceSave(saveLocal, label);
    const unavailable = disabled || !local || saving;
    return <div className="setp__trail-color" aria-busy={saving}>
        <div className="setp__appearance-line">
            <Button size="sm" aria-pressed={color === null} disabled={unavailable || color === null} onClick={() => { void save({ trail_color: null }); }}>{tr('跟随主题')}</Button>
            <ColorSwatches size="sm" aria-label={tr('尾迹预设颜色')} disabled={unavailable} value={color}
                colors={ACCENT_SWATCHES.map(swatch => ({ value: swatch.color, color: swatch.color, label: swatch.label }))}
                onChange={value => { void save({ trail_color: value }); }}/>
        </div>
        <div className="setp__appearance-line">
            <label className="setp__color-picker">
                <span>{tr('自定义颜色')}</span>
                <input type="color" value={draft} disabled={unavailable} onChange={event => setDraft(event.target.value.toUpperCase())}/>
            </label>
            <span className="setp__mono">{draft}</span>
            <Button size="sm" disabled={unavailable || draft === color} onClick={() => { void save({ trail_color: draft }); }}>{tr('应用颜色')}</Button>
        </div>
    </div>;
}

export function PointerStyleControl({ local, saveLocal, label }: AppearanceControlProps) {
    const { style, size } = readPointerAppearance(local);
    const { saving, save } = useAppearanceSave(saveLocal, label);
    return <div className="setp__appearance-line" aria-busy={saving}>
        {style !== 'system' && <span className="setp__pointer-preview" data-style={style} data-size={size} aria-hidden="true">
            <svg viewBox="0 0 32 36" focusable="false"><path d="M4 2v25l7-7 5 12 5-2-5-11 10-1Z"/></svg>
        </span>}
        <Select size="sm" aria-label={label} value={style} disabled={!local || saving}
            onChange={value => { void save({ pointer_style: value as PointerStyle }); }} options={[
                { value: 'system', label: tr('原系统样式') },
                { value: 'white', label: tr('白色箭头') },
                { value: 'black', label: tr('黑色箭头') },
                { value: 'inverted', label: tr('反色箭头') },
            ]}/>
    </div>;
}

export function PointerSizeControl({ local, saveLocal, label }: AppearanceControlProps) {
    const { style, size } = readPointerAppearance(local);
    const { saving, save } = useAppearanceSave(saveLocal, label);
    return <Select size="sm" aria-label={label} value={size} disabled={!local || saving || style === 'system'}
        onChange={value => { void save({ pointer_size: value as PointerSize }); }} options={[
            { value: 'normal', label: tr('标准大小') },
            { value: 'large', label: tr('大号') },
            { value: 'extra_large', label: tr('特大号') },
        ]}/>;
}
