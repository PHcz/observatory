import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import PanelReorderRow from '$lib/components/PanelReorderRow.svelte';
import { settingsStore } from '$lib/stores/settings';

const props = (over = {}) => ({
  panelKey: 'lightning' as const,
  label: 'Lightning',
  index: 2,
  count: 5,
  reorder: vi.fn(),
  ...over,
});

describe('PanelReorderRow', () => {
  beforeEach(() => settingsStore.resetToDefaults());

  it('renders a grip handle and the label', () => {
    const { container, getByText } = render(PanelReorderRow, { props: props() });
    expect(container.querySelector('[data-reorder-handle]')).not.toBeNull();
    expect(getByText('Lightning')).toBeInTheDocument();
  });

  it('root carries data-reorder-item and data-index', () => {
    const { container } = render(PanelReorderRow, { props: props({ index: 3 }) });
    const root = container.querySelector('[data-reorder-item]') as HTMLElement;
    expect(root).not.toBeNull();
    expect(root.getAttribute('data-index')).toBe('3');
  });

  it('up button calls reorder(index, index-1)', async () => {
    const reorder = vi.fn();
    const { getByLabelText } = render(PanelReorderRow, { props: props({ index: 2, reorder }) });
    await fireEvent.click(getByLabelText('Move Lightning up'));
    expect(reorder).toHaveBeenCalledWith(2, 1);
  });

  it('down button calls reorder(index, index+1)', async () => {
    const reorder = vi.fn();
    const { getByLabelText } = render(PanelReorderRow, { props: props({ index: 2, reorder }) });
    await fireEvent.click(getByLabelText('Move Lightning down'));
    expect(reorder).toHaveBeenCalledWith(2, 3);
  });

  it('disables up at the first row and down at the last row', () => {
    const first = render(PanelReorderRow, { props: props({ index: 0, count: 5 }) });
    expect((first.getByLabelText('Move Lightning up') as HTMLButtonElement).disabled).toBe(true);
    // @testing-library/svelte binds queries to document.body (not the per-render
    // container), so a second un-cleaned render collides on the shared "Lightning"
    // label text. Unmount the first render before mounting the second.
    first.unmount();
    const last = render(PanelReorderRow, { props: props({ index: 4, count: 5 }) });
    expect((last.getByLabelText('Move Lightning down') as HTMLButtonElement).disabled).toBe(true);
  });

  it('ArrowUp on the grip calls reorder(index, index-1)', async () => {
    const reorder = vi.fn();
    const { container } = render(PanelReorderRow, { props: props({ index: 2, reorder }) });
    const grip = container.querySelector('[data-reorder-handle]') as HTMLElement;
    await fireEvent.keyDown(grip, { key: 'ArrowUp' });
    expect(reorder).toHaveBeenCalledWith(2, 1);
  });

  it('the visibility switch still toggles settingsStore.panels[panelKey]', async () => {
    const { container } = render(PanelReorderRow, { props: props() });
    const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(input.checked).toBe(true);
    await fireEvent.click(input);
    expect(get(settingsStore).panels.lightning).toBe(false);
  });
});
