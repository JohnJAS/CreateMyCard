import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { CardPreview, parseInput, resolveAppVersion, resolveCardSize, type RendererDocument } from '@widget-debug/card-renderer';
import type { PostprocessArtifact } from '../batchApi';
import { DEFAULT_ASSET_BASE_URL } from '../config';

type RecordRow = Record<string, unknown>;

function records(value: unknown): RecordRow[] {
  return Array.isArray(value) ? value.filter((item): item is RecordRow => (
    Boolean(item) && typeof item === 'object' && !Array.isArray(item)
  )) : [];
}

function displayValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join('、');
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function RecordTable({ rows }: { rows: RecordRow[] }) {
  const columns = useMemo(() => Array.from(new Set(rows.flatMap(Object.keys))), [rows]);
  if (!rows.length) return <div className="postprocess-empty">暂无记录</div>;
  return <div className="postprocess-artifact-table-scroll"><table className="postprocess-artifact-table">
    <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => (
      <td key={column}>{displayValue(row[column])}</td>
    ))}</tr>)}</tbody>
  </table></div>;
}

function GroupedTable({ rows }: { rows: RecordRow[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set<number>());
  const outerColumns = useMemo(() => {
    const keys = new Set<string>();
    rows.forEach((row) => Object.keys(row).forEach((key) => {
      if (key !== 'items') keys.add(key);
    }));
    return Array.from(keys);
  }, [rows]);
  const detailColumns = useMemo(() => {
    const keys = new Set<string>();
    rows.forEach((row) => records(row.items).forEach((item) => {
      Object.keys(item).forEach((key) => keys.add(key));
    }));
    return Array.from(keys);
  }, [rows]);
  if (!rows.length) return <div className="postprocess-empty">暂无记录</div>;
  const toggle = (index: number) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index); else next.add(index);
      return next;
    });
  };
  return <div className="postprocess-artifact-table-scroll"><table className="postprocess-artifact-table postprocess-grouped-table">
    <thead><tr>{outerColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => {
      const items = records(row.items);
      const isOpen = expanded.has(index);
      const label = displayValue(row[outerColumns[0] ?? '']);
      return [
        <tr key={`group-${index}`} className="postprocess-grouped-row">
          {outerColumns.map((column, columnIndex) => <td key={column}>
            {columnIndex === 0
              ? <button type="button" className="postprocess-grouped-toggle" aria-expanded={isOpen}
                  aria-label={`${isOpen ? '收起' : '展开'} ${label} 细则`} onClick={() => toggle(index)}>
                  <span className="postprocess-grouped-chevron" aria-hidden="true" />
                  {label}
                </button>
              : displayValue(row[column])}
          </td>)}
        </tr>,
        isOpen ? <tr key={`detail-${index}`} className="postprocess-grouped-detail">
          <td colSpan={outerColumns.length}>
            {items.length ? <table className="postprocess-artifact-table">
              <thead><tr>{detailColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
              <tbody>{items.map((item, itemIndex) => <tr key={itemIndex}>
                {detailColumns.map((column) => <td key={column}>{displayValue(item[column])}</td>)}
              </tr>)}</tbody>
            </table> : <div className="postprocess-empty">暂无细则</div>}
          </td>
        </tr> : null,
      ];
    })}</tbody>
  </table></div>;
}

function BarChart({ rows }: { rows: RecordRow[] }) {
  const numericKey = Object.keys(rows[0] ?? {}).find((key) => typeof rows[0]?.[key] === 'number');
  const labelKey = Object.keys(rows[0] ?? {}).find((key) => key !== numericKey);
  const maximum = Math.max(1, ...rows.map((row) => Number(row[numericKey ?? ''] ?? 0)));
  if (!numericKey) return <RecordTable rows={rows} />;
  return <div className="postprocess-bar-chart" aria-label="柱状图">
    {rows.map((row, index) => {
      const value = Number(row[numericKey] ?? 0);
      return <div className="postprocess-bar-row" key={index}>
        <span>{displayValue(row[labelKey ?? ''])}</span>
        <div><i style={{ width: `${Math.max(2, value / maximum * 100)}%` }} /></div>
        <b>{displayValue(value)}</b>
      </div>;
    })}
  </div>;
}

function LineChart({ rows }: { rows: RecordRow[] }) {
  const numericKey = Object.keys(rows[0] ?? {}).find((key) => typeof rows[0]?.[key] === 'number');
  if (!numericKey || rows.length < 2) return <RecordTable rows={rows} />;
  const values = rows.map((row) => Number(row[numericKey] ?? 0));
  const maximum = Math.max(1, ...values);
  const points = values.map((value, index) => {
    const x = rows.length === 1 ? 0 : index * 100 / (rows.length - 1);
    return `${x},${100 - value * 90 / maximum}`;
  }).join(' ');
  return <div className="postprocess-line-chart">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="折线图">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
    <RecordTable rows={rows} />
  </div>;
}

function PieChart({ rows }: { rows: RecordRow[] }) {
  const numericKey = Object.keys(rows[0] ?? {}).find((key) => typeof rows[0]?.[key] === 'number');
  const labelKey = Object.keys(rows[0] ?? {}).find((key) => key !== numericKey);
  if (!numericKey) return <RecordTable rows={rows} />;
  const total = rows.reduce((sum, row) => sum + Number(row[numericKey] ?? 0), 0) || 1;
  let cursor = 0;
  const colors = ['#0a59f7', '#28a46b', '#f29b38', '#db3b47', '#77849b'];
  const stops = rows.map((row, index) => {
    const start = cursor;
    cursor += Number(row[numericKey] ?? 0) * 100 / total;
    return `${colors[index % colors.length]} ${start}% ${cursor}%`;
  });
  return <div className="postprocess-pie-layout">
    <div className="postprocess-pie" style={{ background: `conic-gradient(${stops.join(',')})` }} />
    <ul>{rows.map((row, index) => <li key={index}>
      <i style={{ background: colors[index % colors.length] }} />
      <span>{displayValue(row[labelKey ?? ''])}</span><b>{displayValue(row[numericKey])}</b>
    </li>)}</ul>
  </div>;
}

function MatrixView({ value }: { value: unknown }) {
  const matrix = value && typeof value === 'object' ? value as RecordRow : {};
  const rowLabels = Array.isArray(matrix.rows) ? matrix.rows.map(String) : [];
  const columnLabels = Array.isArray(matrix.columns) ? matrix.columns.map(String) : [];
  const cells = Array.isArray(matrix.cells) ? matrix.cells : [];
  if (!rowLabels.length || !columnLabels.length) return <pre>{JSON.stringify(value, null, 2)}</pre>;
  const numeric = cells.flatMap((row) => Array.isArray(row) ? row.map(Number) : []);
  const maximum = Math.max(1, ...numeric);
  return <div className="postprocess-matrix" style={{ gridTemplateColumns: `auto repeat(${columnLabels.length}, 1fr)` }}>
    <span />{columnLabels.map((column) => <b key={column}>{column}</b>)}
    {rowLabels.flatMap((row, rowIndex) => [
      <b key={`${row}-label`}>{row}</b>,
      ...columnLabels.map((column, columnIndex) => {
        const valueAtCell = Number((cells[rowIndex] as unknown[] | undefined)?.[columnIndex] ?? 0);
        return <span key={`${row}-${column}`} style={{ '--heat': valueAtCell / maximum } as CSSProperties}>
          {displayValue(valueAtCell)}
        </span>;
      }),
    ])}
  </div>;
}

function RemoteText({ url }: { url: string }) {
  const [text, setText] = useState('正在加载…');
  useEffect(() => {
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then((response) => response.ok ? response.text() : Promise.reject(new Error('读取失败')))
      .then(setText)
      .catch((reason) => { if (reason.name !== 'AbortError') setText(String(reason)); });
    return () => controller.abort();
  }, [url]);
  return <pre>{text}</pre>;
}

function DslGalleryPreview({ item }: { item: RecordRow }) {
  const [result, setResult] = useState<{ document: RendererDocument | null; error: string }>({
    document: null, error: '',
  });
  useEffect(() => {
    const controller = new AbortController();
    setResult({ document: null, error: '' });
    const dsl = typeof item.dsl === 'string' ? item.dsl : '';
    if (dsl) {
      const cardSize = resolveCardSize(null, '', typeof item.size === 'string' ? item.size : '2x2');
      parseInput(dsl, { cardSize, appVersion: resolveAppVersion(item), signal: controller.signal })
        .then((document) => {
          if (!controller.signal.aborted) setResult({ document, error: '' });
        })
        .catch((reason) => {
          if (!controller.signal.aborted) setResult({
            document: null, error: reason instanceof Error ? reason.message : String(reason),
          });
        });
    }
    return () => controller.abort();
  }, [item.dsl, item.size, item.appVersion]);
  if (!result.document) {
    return <div className="postprocess-image-error">{result.error || '正在渲染…'}</div>;
  }
  return <div className={`postprocess-dsl-preview ${item.size === '2x4' ? 'wide' : ''}`}>
    <CardPreview document={result.document} assetBaseUrl={DEFAULT_ASSET_BASE_URL} />
  </div>;
}

function ImageGallery({ items }: { items: RecordRow[] }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [showThumbnails, setShowThumbnails] = useState(false);
  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, items.length - 1)));
  }, [items.length]);
  if (!items.length) return <div className="postprocess-empty">暂无图片</div>;
  const item = items[activeIndex] ?? items[0];
  const url = typeof item.url === 'string' ? item.url : '';
  const dsl = typeof item.dsl === 'string' ? item.dsl : '';
  const status = String(item.status ?? '');
  const errorTypes = Array.isArray(item.errorTypes) ? item.errorTypes.map(String) : [];
  const selectRelative = (offset: number) => {
    setActiveIndex((current) => (current + offset + items.length) % items.length);
  };
  return <div
    className="postprocess-image-gallery"
    tabIndex={0}
    onKeyDown={(event) => {
      if (event.key === 'ArrowLeft') selectRelative(-1);
      if (event.key === 'ArrowRight') selectRelative(1);
    }}
  >
    <div className="postprocess-image-toolbar">
      <span>{activeIndex + 1} / {items.length}</span>
      {items.length > 1 && <div>
        <button type="button" aria-label="上一张图片" onClick={() => selectRelative(-1)}>‹</button>
        <button type="button" aria-label="下一张图片" onClick={() => selectRelative(1)}>›</button>
        <button
          type="button"
          aria-pressed={showThumbnails}
          onClick={() => setShowThumbnails((value) => !value)}
        >{showThumbnails ? '隐藏缩略图' : '显示缩略图'}</button>
      </div>}
    </div>
    <figure key={`${String(item.label ?? '')}-${activeIndex}`}>
      <figcaption><span>{displayValue(item.label)}</span>
        <b className={status === '校验通过' ? 'success' : 'danger'}>{status}</b>
      </figcaption>
      {errorTypes.length > 0 && <p>{errorTypes.join('、')}</p>}
      {url
        ? <a href={url} target="_blank" rel="noreferrer"><img
            src={url}
            alt={String(item.alt ?? item.label ?? '校验 DSL 渲染结果')}
          /></a>
        : dsl
          ? <DslGalleryPreview item={item} />
          : <div className="postprocess-image-error">{displayValue(item.error)}</div>}
    </figure>
    {showThumbnails && items.length > 1 && <div className="postprocess-image-thumbnails">
      {items.map((candidate, index) => {
        const thumbnailUrl = typeof candidate.url === 'string' ? candidate.url : '';
        return <button
          type="button"
          className={index === activeIndex ? 'is-active' : ''}
          aria-label={`查看第 ${index + 1} 张图片`}
          key={`${String(candidate.label ?? '')}-${index}`}
          onClick={() => setActiveIndex(index)}
        >
          {thumbnailUrl
            ? <img src={thumbnailUrl} alt="" />
            : <span>{typeof candidate.dsl === 'string' ? 'DSL' : '错误'}</span>}
          <b>{index + 1}</b>
        </button>;
      })}
    </div>}
  </div>;
}

function ScoreGrid({
  rows,
  onOpenSample,
}: {
  rows: RecordRow[];
  onOpenSample?: (sampleId: string) => void;
}) {
  if (!rows.length) return <div className="postprocess-empty">暂无评分卡</div>;
  return <div className="postprocess-score-grid">
    {rows.map((row, index) => {
      const url = typeof row.url === 'string' ? row.url : '';
      const total = scoreNumber(row.total);
      const band = typeof row.band === 'string' ? row.band : '';
      const status = String(row.status ?? '');
      const verdict = String(row.verdict ?? '');
      const sampleId = String(row.sampleId ?? '');
      const size = String(row.size ?? '2x2');
      const aspect = sizeAspect(size);
      const dimensions = Array.isArray(row.dimensions)
        ? row.dimensions.filter((item): item is RecordRow => (
          Boolean(item) && typeof item === 'object' && !Array.isArray(item)
        ))
        : [];
      const shot = url
        ? <a className="postprocess-score-shot" style={{ aspectRatio: aspect }} href={url}
            target="_blank" rel="noreferrer" aria-label={`查看 ${sampleId} 渲染截图`}
            onClick={(event) => event.stopPropagation()}>
            <img src={url} alt={`${sampleId} 渲染截图`} loading="lazy" />
          </a>
        : <div className="postprocess-score-shot" style={{ aspectRatio: aspect }}>
            <span>无截图</span>
          </div>;
      const openSample = onOpenSample && sampleId ? () => onOpenSample(sampleId) : undefined;
      return <article
        key={`${sampleId}-${index}`}
        className={`postprocess-score-card is-${status || 'unknown'}${openSample ? ' is-clickable' : ''}`}
        role={openSample ? 'link' : undefined}
        tabIndex={openSample ? 0 : undefined}
        aria-label={openSample ? `查看 ${sampleId} 失败项明细` : undefined}
        onClick={openSample}
        onKeyDown={openSample ? (event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            openSample();
          }
        } : undefined}
      >
        {shot}
        <header>
          <b>{sampleId || `样本 ${index + 1}`}</b>
          <span className={`postprocess-score-verdict ${status}`}>{verdict || '—'}</span>
        </header>
        <div className="postprocess-score-total">
          <strong>{total === null ? '—' : total.toFixed(1)}</strong>
          <span>总分 / 100{band ? ` · ${band}` : ''}</span>
        </div>
        <ul>
          {dimensions.map((item, dimensionIndex) => {
            const score = scoreNumber(item.score);
            const max = scoreNumber(item.max);
            const ratio = score !== null && max ? Math.max(0, Math.min(100, score / max * 100)) : 0;
            const applicable = item.applicable !== false;
            const reason = typeof item.reason === 'string' ? item.reason : '不适用';
            const detailRows = Array.isArray(item.items)
              ? item.items.filter((entry): entry is RecordRow => (
                Boolean(entry) && typeof entry === 'object' && !Array.isArray(entry)
              ))
              : [];
            const drops = detailRows
              .filter((entry) => (scoreNumber(entry.deduction) ?? 0) > 0)
              .sort((left, right) => (
                (scoreNumber(right.deduction) ?? 0) - (scoreNumber(left.deduction) ?? 0)
              ));
            const visibleDrops = drops.slice(0, 3);
            const hiddenDrops = drops.length - visibleDrops.length;
            return <li className="postprocess-score-dim"
              key={`${String(item.key ?? item.label ?? dimensionIndex)}-${dimensionIndex}`}>
              <div className="postprocess-score-dim-head">
                <span>{displayValue(item.label)}</span>
                <i><em style={{ width: `${ratio}%` }} /></i>
                <b>{score === null ? '—' : score.toFixed(1)}<small>/{max === null ? '—' : max}</small></b>
              </div>
              {!applicable && <p className="postprocess-score-clear">{reason}</p>}
              {applicable && !drops.length && <p className="postprocess-score-clear">全部通过</p>}
              {applicable && drops.length > 0 && <ul className="postprocess-score-drops">
                {visibleDrops.map((entry, dropIndex) => {
                  const deduction = scoreNumber(entry.deduction);
                  const title = String(entry.title ?? entry.rule ?? '');
                  const expected = entry.expected ? `期望：${String(entry.expected)}` : '';
                  const actual = entry.actual ? `实际：${String(entry.actual)}` : '';
                  const hint = [expected, actual].filter(Boolean).join('；');
                  const pending = String(entry.status ?? '') === 'pending';
                  return <li key={`${title}-${dropIndex}`} title={hint}>
                    <span>{pending ? '待复核 ' : ''}{title}{entry.actual ? <em>{String(entry.actual)}</em> : null}</span>
                    <b>−{deduction === null ? '—' : deduction.toFixed(1)}</b>
                  </li>;
                })}
                {hiddenDrops > 0 && <li className="postprocess-score-more">
                  另有 {hiddenDrops} 条规则扣分，见样本的失败项明细
                </li>}
              </ul>}
            </li>;
          })}
          {!dimensions.length && <li className="muted">暂无维度分</li>}
        </ul>
        {openSample && <footer className="postprocess-score-open">查看失败项明细 →</footer>}
      </article>;
    })}
  </div>;
}

function scoreNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function sizeAspect(size: string): string {
  const match = /^(\d+)x(\d+)$/i.exec(size.trim());
  if (!match) return '1 / 1';
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!width || !height) return '1 / 1';
  return `${width} / ${height}`;
}

export function PostprocessArtifactView({
  artifact,
  onOpenSample,
}: {
  artifact: PostprocessArtifact;
  onOpenSample?: (sampleId: string) => void;
}) {
  const rows = records(artifact.data);
  const renderer = artifact.renderer;
  let body: ReactNode;
  if (artifact.dataType === 'metrics') {
    body = <div className="postprocess-kpis">{rows.map((item, index) => {
      const text = displayValue(item.value);
      return <div key={index}>
        <b className={text.length > 12 ? 'long' : undefined}>{text}
          {item.unit ? <small>{String(item.unit)}</small> : null}</b>
        <span>{displayValue(item.label)}</span>
      </div>;
    })}</div>;
  } else if (artifact.dataType === 'records' && renderer === 'score-grid') {
    body = <ScoreGrid rows={rows} onOpenSample={onOpenSample} />;
  } else if (artifact.dataType === 'records' && renderer === 'grouped-table') {
    body = <GroupedTable rows={rows} />;
  } else if (artifact.dataType === 'records' && renderer === 'bar') {
    body = <BarChart rows={rows} />;
  } else if (artifact.dataType === 'records' && renderer === 'line') {
    body = <LineChart rows={rows} />;
  } else if (artifact.dataType === 'records' && renderer === 'pie') {
    body = <PieChart rows={rows} />;
  } else if (artifact.dataType === 'records' || artifact.dataType === 'issues') {
    body = <RecordTable rows={rows} />;
  } else if (artifact.dataType === 'matrix') {
    body = <MatrixView value={artifact.data} />;
  } else if (artifact.dataType === 'image' && renderer === 'gallery' && (rows.length > 0 || !artifact.url)) {
    body = <ImageGallery items={rows} />;
  } else if (artifact.dataType === 'image' && artifact.url) {
    body = <figure><img src={artifact.url} alt={artifact.alt ?? artifact.title ?? '插件图片产物'} />
      {artifact.fullUrl ? <a href={String(artifact.fullUrl)} target="_blank" rel="noreferrer">查看原图 ↗</a> : null}
    </figure>;
  } else if ((artifact.dataType === 'link' || artifact.dataType === 'file') && artifact.url) {
    body = <a className="postprocess-file-link" href={artifact.url} target="_blank" rel="noreferrer">
      {artifact.label ?? (artifact.dataType === 'file' ? '下载文件' : '打开链接')} ↗
    </a>;
  } else if ((artifact.dataType === 'code' || artifact.dataType === 'diff') && artifact.url) {
    body = <RemoteText url={artifact.url} />;
  } else if (artifact.dataType === 'code' || artifact.dataType === 'diff') {
    body = <pre>{displayValue(artifact.data ?? artifact.text)}</pre>;
  } else if (artifact.dataType === 'text') {
    body = <p>{displayValue(artifact.data ?? artifact.text)}</p>;
  } else {
    body = <pre>{JSON.stringify(artifact.data ?? artifact, null, 2)}</pre>;
  }
  const wide = artifact.wide === true ? ' wide' : '';
  if (artifact.collapsible === true) {
    return <details className={`postprocess-artifact ${artifact.dataType}${wide} collapsible`}>
      <summary>
        <h3>{artifact.title ?? artifact.key}</h3>
        <span className="postprocess-artifact-toggle" aria-hidden="true" />
      </summary>
      {body}
    </details>;
  }
  return <section className={`postprocess-artifact ${artifact.dataType}${wide}`}>
    <h3>{artifact.title ?? artifact.key}</h3>{body}
  </section>;
}
