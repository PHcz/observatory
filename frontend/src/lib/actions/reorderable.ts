// Zero-dependency pointer-drag reordering for a vertical list. Rows carry
// [data-reorder-item] + data-index; drag handles carry [data-reorder-handle].
// Unified mouse + touch via Pointer Events. Commits once, on pointerup.
interface Params {
  onReorder: (from: number, to: number) => void;
}

export function reorderable(node: HTMLElement, params: Params) {
  let onReorder = params.onReorder;
  let fromIndex = -1;
  let items: HTMLElement[] = [];
  let dragRow: HTMLElement | null = null;
  let overRow: HTMLElement | null = null;

  const rowFor = (el: EventTarget | null): HTMLElement | null =>
    el instanceof Element ? (el.closest('[data-reorder-item]') as HTMLElement | null) : null;

  function clearMarks() {
    for (const it of items) {
      it.classList.remove('reorder-over-before', 'reorder-over-after');
    }
  }

  function targetIndexFor(clientY: number): number {
    // Insert before the first row whose vertical midpoint is below the pointer;
    // otherwise append after the last row.
    for (let i = 0; i < items.length; i++) {
      const r = items[i].getBoundingClientRect();
      if (clientY < r.top + r.height / 2) return i;
    }
    return items.length;
  }

  function onPointerMove(e: PointerEvent) {
    if (fromIndex < 0) return;
    e.preventDefault();
    let target = targetIndexFor(e.clientY);
    clearMarks();
    // Show an insertion line. target === items.length → after the last row.
    const markIdx = Math.min(target, items.length - 1);
    overRow = items[markIdx] ?? null;
    if (overRow) {
      overRow.classList.add(target > markIdx ? 'reorder-over-after' : 'reorder-over-before');
    }
  }

  function cleanup() {
    clearMarks();
    dragRow?.classList.remove('reorder-dragging');
    fromIndex = -1;
    dragRow = null;
    overRow = null;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerCancel);
  }

  function onPointerUp(e: PointerEvent) {
    if (fromIndex < 0) return;
    let target = targetIndexFor(e.clientY);
    // Removing the dragged row before re-inserting shifts later targets down by one.
    if (target > fromIndex) target -= 1;
    const from = fromIndex;
    cleanup();
    if (target !== from && target >= 0) onReorder(from, target);
  }

  function onPointerCancel() {
    if (fromIndex < 0) return;
    cleanup();
  }

  function onPointerDown(e: PointerEvent) {
    const handle = (e.target as Element).closest('[data-reorder-handle]');
    if (!handle) return;
    const row = rowFor(e.target);
    if (!row) return;
    e.preventDefault();
    items = Array.from(node.querySelectorAll<HTMLElement>('[data-reorder-item]'));
    fromIndex = items.indexOf(row);
    dragRow = row;
    row.classList.add('reorder-dragging');
    window.addEventListener('pointermove', onPointerMove, { passive: false });
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerCancel);
  }

  node.addEventListener('pointerdown', onPointerDown);

  return {
    update(p: Params) {
      onReorder = p.onReorder;
    },
    destroy() {
      node.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerCancel);
    },
  };
}
