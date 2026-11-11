// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { OinkProvider, Toaster, toast } from 'oink-ui';
import type { ReactNode } from 'react';
import { setLanguage } from '../i18n';
import type { LocalPreferences } from './model';
import { PointerSizeControl, PointerStyleControl, readPointerAppearance, TrailColorControl } from './PointerAppearance';

beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) });
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
    HTMLElement.prototype.scrollIntoView = () => {};
});
beforeEach(() => setLanguage('zh-Hans'));
afterEach(() => { toast.dismiss(); cleanup(); vi.restoreAllMocks(); });

const local = (patch: Partial<LocalPreferences> = {}) => ({ trail_color: null, pointer_style: 'system', pointer_size: 'normal', ...patch }) as LocalPreferences;
const wrap = (node: ReactNode) => <OinkProvider defaultMotion="reduced">{node}<Toaster/></OinkProvider>;

describe('appearance fallback', () => {
    it.each([undefined, null, {}, { trail_color: '#123', pointer_style: 'unknown', pointer_size: 'huge' }, { trail_color: 'red' }])('uses safe defaults for legacy/invalid snapshot %s', snapshot => {
        expect(readPointerAppearance(snapshot as Partial<LocalPreferences>)).toEqual({ color: null, style: 'system', size: 'normal' });
    });
    it('normalizes valid colors without changing explicit Windows choices', () => {
        expect(readPointerAppearance(local({ trail_color: '#12abef', pointer_style: 'inverted', pointer_size: 'extra_large' }))).toEqual({ color: '#12ABEF', style: 'inverted', size: 'extra_large' });
    });
});

it('saves preset, arbitrary and follow-theme colors without changing the theme', async () => {
    const saveLocal = vi.fn().mockResolvedValue(undefined);
    const props = { local: local(), saveLocal, label: '尾迹颜色' };
    const { getByRole, getByLabelText, rerender } = render(wrap(<TrailColorControl {...props}/>));
    expect(getByRole('button', { name: '跟随主题' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(getByRole('radio', { name: '蓝' }));
    await waitFor(() => expect(saveLocal).toHaveBeenCalledExactlyOnceWith({ trail_color: '#2E7BFF' }));
    rerender(wrap(<TrailColorControl {...props} local={local({ trail_color: '#2E7BFF' })}/>));
    expect(getByRole('radio', { name: '蓝' }).getAttribute('aria-checked')).toBe('true');
    saveLocal.mockClear();
    const picker = getByLabelText('自定义颜色') as HTMLInputElement;
    expect(picker.type).toBe('color');
    fireEvent.change(picker, { target: { value: '#123abc' } });
    expect(saveLocal).not.toHaveBeenCalled();
    fireEvent.click(getByRole('button', { name: '应用颜色' }));
    await waitFor(() => expect(saveLocal).toHaveBeenCalledExactlyOnceWith({ trail_color: '#123ABC' }));
    rerender(wrap(<TrailColorControl {...props} local={local({ trail_color: '#123ABC' })}/>));
    expect(picker.value).toBe('#123abc');
    saveLocal.mockClear();
    fireEvent.click(getByRole('button', { name: '跟随主题' }));
    await waitFor(() => expect(saveLocal).toHaveBeenCalledExactlyOnceWith({ trail_color: null }));
});

it('does not report a failed color save as an applied appearance', async () => {
    const saveLocal = vi.fn().mockRejectedValue(new Error('unavailable'));
    const { getByRole } = render(wrap(<TrailColorControl local={local()} saveLocal={saveLocal} label="尾迹颜色"/>));
    fireEvent.click(getByRole('radio', { name: '蓝' }));
    await within(document.body).findByText('无法更改「尾迹颜色」');
    expect(getByRole('button', { name: '跟随主题' }).getAttribute('aria-pressed')).toBe('true');
    expect(getByRole('radio', { name: '蓝' }).getAttribute('aria-checked')).toBe('false');
});

it('keeps the color controls unavailable while the trail master is off', () => {
    const saveLocal = vi.fn();
    const { getByRole, getByLabelText } = render(wrap(<TrailColorControl local={local({ trail_color: '#123456' })} saveLocal={saveLocal} label="尾迹颜色" disabled/>));
    expect((getByRole('button', { name: '跟随主题' }) as HTMLButtonElement).disabled).toBe(true);
    expect((getByLabelText('自定义颜色') as HTMLInputElement).disabled).toBe(true);
    expect((getByRole('button', { name: '应用颜色' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(getByRole('radio', { name: '蓝' }));
    expect(saveLocal).not.toHaveBeenCalled();
});

it('selects Windows arrow style and size independently and can restore the original style', async () => {
    const saveLocal = vi.fn().mockResolvedValue(undefined);
    const controls = (value: LocalPreferences) => wrap(<>
        <PointerStyleControl local={value} saveLocal={saveLocal} label="鼠标箭头样式"/>
        <PointerSizeControl local={value} saveLocal={saveLocal} label="箭头大小"/>
    </>);
    const { getByRole, rerender } = render(controls(local()));
    const style = getByRole('combobox', { name: '鼠标箭头样式' });
    const size = getByRole('combobox', { name: '箭头大小' }) as HTMLButtonElement;
    expect(style.textContent).toContain('原系统样式');
    expect(size.disabled).toBe(true);
    fireEvent.click(style);
    for (const name of ['原系统样式', '白色箭头', '黑色箭头', '反色箭头']) expect(await within(document.body).findByRole('option', { name })).toBeTruthy();
    fireEvent.click(within(document.body).getByRole('option', { name: '反色箭头' }));
    await waitFor(() => expect(saveLocal).toHaveBeenCalledExactlyOnceWith({ pointer_style: 'inverted' }));
    rerender(controls(local({ pointer_style: 'inverted' })));
    expect(size.disabled).toBe(false);
    saveLocal.mockClear();
    fireEvent.click(size);
    fireEvent.click(await within(document.body).findByRole('option', { name: '特大号' }));
    await waitFor(() => expect(saveLocal).toHaveBeenCalledExactlyOnceWith({ pointer_size: 'extra_large' }));
    rerender(controls(local({ pointer_style: 'inverted', pointer_size: 'extra_large' })));
    expect(size.textContent).toContain('特大号');
    saveLocal.mockClear();
    fireEvent.click(style);
    fireEvent.click(await within(document.body).findByRole('option', { name: '原系统样式' }));
    await waitFor(() => expect(saveLocal).toHaveBeenCalledExactlyOnceWith({ pointer_style: 'system' }));
    rerender(controls(local({ pointer_style: 'system', pointer_size: 'extra_large' })));
    expect(size.disabled).toBe(true);
    expect(size.textContent).toContain('特大号');
});
