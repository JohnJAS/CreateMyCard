// 只读取当前渲染画面；不改变 DOM、DSL 或滚动位置。
// 由 Playwright 以 locator.evaluate 执行，因此不能依赖外部闭包。
export function collectTargetEvidence(root, meta = {}) {
  const surface = root.querySelector('.card-renderer__surface') || root;
  const frame = surface.getBoundingClientRect();
  const relative = (rect) => ({
    x: rect.x - frame.x,
    y: rect.y - frame.y,
    width: rect.width,
    height: rect.height,
  });
  const number = (value) => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const visible = (el) => {
    for (let node = el; node && node !== surface.parentElement; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
        return false;
      }
    }
    return true;
  };
  const intersects = (rect, region) => rect.width > 0 && rect.height > 0
    && rect.right > region.left + 0.5 && rect.left < region.right - 0.5
    && rect.bottom > region.top + 0.5 && rect.top < region.bottom - 0.5;
  const contentRect = (rect, style) => relative({
    x: rect.x + number(style.borderLeftWidth) + number(style.paddingLeft),
    y: rect.y + number(style.borderTopWidth) + number(style.paddingTop),
    width: rect.width - number(style.borderLeftWidth) - number(style.borderRightWidth)
      - number(style.paddingLeft) - number(style.paddingRight),
    height: rect.height - number(style.borderTopWidth) - number(style.borderBottomWidth)
      - number(style.paddingTop) - number(style.paddingBottom),
  });
  const ancestry = (el) => {
    const chain = [];
    for (let node = el.parentElement; node && node !== surface.parentElement; node = node.parentElement) {
      const style = getComputedStyle(node);
      chain.push({
        id: node.getAttribute('data-node-id'),
        tag: node.tagName,
        box: relative(node.getBoundingClientRect()),
        overflowX: style.overflowX,
        overflowY: style.overflowY,
      });
    }
    return chain;
  };
  const clippingRegion = (el, chain) => {
    let region = { left: frame.left, top: frame.top, right: frame.right, bottom: frame.bottom };
    const own = getComputedStyle(el);
    if (/hidden|clip/.test(`${own.overflowX} ${own.overflowY}`)) {
      const rect = el.getBoundingClientRect();
      region = {
        left: Math.max(region.left, rect.left),
        top: Math.max(region.top, rect.top),
        right: Math.min(region.right, rect.right),
        bottom: Math.min(region.bottom, rect.bottom),
      };
    }
    for (const entry of chain) {
      if (!/hidden|clip/.test(`${entry.overflowX} ${entry.overflowY}`)) continue;
      const rect = entry.box;
      region = {
        left: Math.max(region.left, rect.x + frame.x),
        top: Math.max(region.top, rect.y + frame.y),
        right: Math.min(region.right, rect.x + frame.x + rect.width),
        bottom: Math.min(region.bottom, rect.y + frame.y + rect.height),
      };
    }
    return region;
  };
  const textDetails = (el) => {
    const chain = ancestry(el);
    const region = clippingRegion(el, chain);
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    const lineRects = [];
    const parts = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const text = node.textContent || '';
      if (!text.trim() || !node.parentElement) continue;
      if (node.parentElement.closest('[data-node-id]') !== el) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rects = Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
      if (!rects.length) continue;
      const visibleRects = rects.map(relative);
      textNodes.push({ text, rects: visibleRects });
      lineRects.push(...visibleRects);
      const clipped = rects.some((rect) => !intersects(rect, region));
      if (!clipped) {
        parts.push(text);
        continue;
      }
      const chars = Array.from(text);
      let offset = 0;
      for (const char of chars) {
        if (offset >= 512) break;
        const start = offset;
        offset += char.length;
        if (/\s/.test(char)) {
          parts.push(char);
          continue;
        }
        const charRange = document.createRange();
        charRange.setStart(node, start);
        charRange.setEnd(node, offset);
        const charRects = Array.from(charRange.getClientRects());
        if (charRects.some((rect) => intersects(rect, region))) parts.push(char);
      }
    }
    lineRects.sort((a, b) => (a.y - b.y) || (a.x - b.x));
    return { textNodes, lineRects, renderedText: parts.join('') };
  };
  const nodes = [];
  for (const el of surface.querySelectorAll('[data-node-id]')) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const image = el.tagName === 'IMG' ? el : el.querySelector('img');
    const chain = ancestry(el);
    const parentId = chain.find((entry) => entry.id)?.id ?? null;
    const text = textDetails(el);
    const zeroSized = rect.width === 0 && rect.height === 0;
    nodes.push({
      id: el.getAttribute('data-node-id'),
      tag: el.tagName,
      leaf: el.querySelector('[data-node-id]') === null,
      text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
      renderedText: text.renderedText.replace(/\s+/g, ' ').trim(),
      box: relative(rect),
      contentRect: contentRect(rect, style),
      lineRects: text.lineRects,
      textNodes: text.textNodes,
      lineCount: new Set(text.lineRects.map((item) => Math.round(item.y / 2))).size,
      parentId,
      ancestors: chain,
      clipChain: chain.filter((entry) => /hidden|clip/.test(`${entry.overflowX} ${entry.overflowY}`)),
      zeroSized,
      style: {
        display: style.display,
        visibility: style.visibility,
        boxSizing: style.boxSizing,
        position: style.position,
        zIndex: style.zIndex,
        fontSize: Number.parseFloat(style.fontSize) || 0,
        fontWeight: style.fontWeight,
        color: style.color,
        backgroundColor: style.backgroundColor,
        lineHeight: style.lineHeight,
        textOverflow: style.textOverflow,
        webkitLineClamp: style.webkitLineClamp,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        maxLines: style.maxLines,
        opacity: style.opacity,
        padding: style.padding,
        margin: style.margin,
        flexDirection: style.flexDirection,
        alignItems: style.alignItems,
        justifyContent: style.justifyContent,
        gap: style.gap,
        borderRadius: style.borderRadius,
      },
      clientWidth: el.clientWidth,
      clientHeight: el.clientHeight,
      scrollWidth: el.scrollWidth,
      scrollHeight: el.scrollHeight,
      visible: visible(el),
      image: image ? {
        src: image.getAttribute('src'),
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight,
        complete: image.complete,
        ariaLabel: image.getAttribute('aria-label'),
        objectFit: getComputedStyle(image).objectFit,
        box: relative(image.getBoundingClientRect()),
      } : null,
    });
  }
  const renderedVisibleText = nodes
    .filter((node) => node.leaf && node.visible !== false && node.renderedText)
    .map((node) => node.renderedText)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
  return {
    schemaVersion: 'target-dom-v2',
    size: typeof meta.size === 'string' ? meta.size : null,
    scale: Number(meta.scale) || window.devicePixelRatio,
    surface: relative(frame),
    visibleText: (surface.innerText || '').replace(/\s+/g, ' ').trim(),
    renderedVisibleText,
    nodes,
    devicePixelRatio: window.devicePixelRatio,
  };
}
