import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PostprocessArtifact } from '../../../../platform/src/batchApi';
import { PostprocessArtifactView } from '../../../../platform/src/components/PostprocessArtifactView';

describe('PostprocessArtifactView', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  it.each([
    ['metrics', 'kpi', [{ label: '召回率', value: 87.5, unit: '%' }], '87.5'],
    ['records', 'table', [{ component: 'SingleLineTitle', matched: 3 }], 'SingleLineTitle'],
    ['records', 'bar', [{ range: '80–100%', count: 4 }], '80–100%'],
    ['records', 'line', [{ day: '一', count: 1 }, { day: '二', count: 2 }], '二'],
    ['records', 'pie', [{ state: '通过', count: 2 }], '通过'],
    ['matrix', 'heatmap', { rows: ['Card'], columns: ['命中'], cells: [[3]] }, 'Card'],
    ['issues', 'issues', [{ message: '组件缺失' }], '组件缺失'],
    ['json', 'tree', { nested: { value: 1 } }, 'nested'],
    ['text', undefined, '纯文本结果', '纯文本结果'],
    ['code', 'code', '["a", "SingleLineTitle"]', 'SingleLineTitle'],
    ['diff', 'diff', '- old\n+ new', '+ new'],
  ] as Array<[string, string | undefined, unknown, string]>) (
    'renders %s through the controlled registry',
    (dataType, renderer, data, expected) => {
      const { container } = render(<PostprocessArtifactView artifact={{
        key: `${dataType}-${renderer ?? 'default'}`,
        title: '测试产物',
        dataType,
        renderer,
        data,
      } as PostprocessArtifact} />);

      expect(container).toHaveTextContent(expected);
    },
  );

  it('marks wide artifacts for a full-row layout', () => {
    const { container, rerender } = render(<PostprocessArtifactView artifact={{
      key: 'rules', title: '细分维度平均', dataType: 'records', renderer: 'table',
      data: [{ 维度: '规范符合' }], wide: true,
    }} />);
    expect(container.querySelector('.postprocess-artifact')).toHaveClass('wide');

    rerender(<PostprocessArtifactView artifact={{
      key: 'rules', title: '细分维度平均', dataType: 'records', renderer: 'table',
      data: [{ 维度: '规范符合' }],
    }} />);
    expect(container.querySelector('.postprocess-artifact')).not.toHaveClass('wide');
  });

  it('limits score cards to the top three deductions', () => {
    render(<PostprocessArtifactView artifact={{
      key: 'scores', title: '卡片评分总览', dataType: 'records', renderer: 'score-grid',
      data: [{
        sampleId: 'Q001', status: 'failed', verdict: '失败', total: 60.0, band: '不合格', size: '2x2',
        dimensions: [{
          key: 'spec', label: '规范符合', score: 5.0, max: 25.0, applicable: true, items: [
            { rule: 'SPEC.A', title: '规则 A', deduction: 1.0 },
            { rule: 'SPEC.B', title: '规则 B', deduction: 5.0 },
            { rule: 'SPEC.C', title: '规则 C', deduction: 2.0 },
            { rule: 'SPEC.D', title: '规则 D', deduction: 3.0 },
          ],
        }],
      }],
    }} />);
    expect(screen.getByText('规则 B')).toBeInTheDocument();
    expect(screen.getByText('规则 D')).toBeInTheDocument();
    expect(screen.getByText('规则 C')).toBeInTheDocument();
    expect(screen.queryByText('规则 A')).not.toBeInTheDocument();
    expect(screen.getByText('另有 1 条规则扣分，见样本的失败项明细')).toBeInTheDocument();
  });

  it('opens the sample detail page from a score card when a handler is provided', () => {
    const openSample = vi.fn();
    const artifact = {
      key: 'scores', title: '卡片评分总览', dataType: 'records', renderer: 'score-grid',
      data: [{
        sampleId: 'Q001', status: 'failed', verdict: '失败', total: 60.0, size: '2x2',
        dimensions: [],
      }],
    } as PostprocessArtifact;
    const { rerender } = render(<PostprocessArtifactView artifact={artifact}
      onOpenSample={openSample} />);
    const card = screen.getByRole('link', { name: '查看 Q001 失败项明细' });
    expect(screen.getByText('查看失败项明细 →')).toBeInTheDocument();
    fireEvent.click(card);
    expect(openSample).toHaveBeenCalledWith('Q001');
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(openSample).toHaveBeenCalledTimes(2);

    rerender(<PostprocessArtifactView artifact={artifact} />);
    expect(screen.queryByRole('link', { name: '查看 Q001 失败项明细' })).not.toBeInTheDocument();
    expect(screen.queryByText('查看失败项明细 →')).not.toBeInTheDocument();
  });

  it('expands grouped rows to show rule details per dimension', () => {
    render(<PostprocessArtifactView artifact={{
      key: 'rules', title: '细分维度平均', dataType: 'records', renderer: 'grouped-table',
      data: [
        {
          维度: '目标语义', '均分 / 满分': '40.0 / 40', 通过率: '100%', 计分样本: 6,
          items: [{
            规则: 'TARGET.DAYS_MISMATCH 天数', 含义: '天数须与期望一致',
            '均分 / 满分': '40.0 / 40', 通过率: '100%', 参与样本: 6,
          }],
        },
        {
          维度: '规范符合', '均分 / 满分': '12.5 / 25', 通过率: '50%', 计分样本: 6,
          items: [{
            规则: 'SPEC.TITLE_COLOR 标题颜色', 含义: '标题使用主色',
            '均分 / 满分': '12.5 / 25', 通过率: '50%', 参与样本: 6,
          }],
        },
      ],
    }} />);
    expect(screen.getByText('目标语义')).toBeInTheDocument();
    expect(screen.queryByText('天数须与期望一致')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '展开 目标语义 细则' }));
    expect(screen.getByText('天数须与期望一致')).toBeInTheDocument();
    expect(screen.queryByText('标题使用主色')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '展开 规范符合 细则' }));
    expect(screen.getByText('标题使用主色')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '收起 目标语义 细则' }));
    expect(screen.queryByText('天数须与期望一致')).not.toBeInTheDocument();
  });

  it('renders collapsible artifacts as a closed details panel', () => {
    const { container } = render(<PostprocessArtifactView artifact={{
      key: 'rules', title: '细分维度平均', dataType: 'records', renderer: 'table',
      data: [{ 细分维度: '规范符合 · SPEC.TITLE_COLOR' }], wide: true, collapsible: true,
    }} />);
    const panel = container.querySelector<HTMLDetailsElement>('details.postprocess-artifact');
    if (!panel) throw new Error('缺少可折叠产物容器');
    expect(panel.open).toBe(false);
    expect(panel).toHaveClass('wide', 'collapsible');
    expect(panel.querySelector('summary')).toHaveTextContent('细分维度平均');
    expect(panel).toHaveTextContent('SPEC.TITLE_COLOR');
  });

  it('renders images and restricted download links without executable markup', () => {
    const { rerender } = render(<PostprocessArtifactView artifact={{
      key: 'capture',
      title: '截图',
      dataType: 'image',
      url: '/capture.png',
      alt: '样本截图',
    }} />);
    expect(screen.getByRole('img', { name: '样本截图' })).toHaveAttribute('src', '/capture.png');

    rerender(<PostprocessArtifactView artifact={{
      key: 'download',
      title: '文件',
      dataType: 'file',
      url: '/artifact.txt',
    }} />);
    expect(screen.getByRole('link', { name: /下载文件/ })).toHaveAttribute('href', '/artifact.txt');
  });

  it('navigates validation images and keeps failed captures visible', () => {
    render(<PostprocessArtifactView artifact={{
      key: 'validation-renders',
      title: '逐次校验 DSL 浏览器渲染结果',
      dataType: 'image',
      renderer: 'gallery',
      data: [
        {
          label: '执行尝试 1 · 接口调用 1 · 校验评估 1',
          status: '校验失败',
          errorTypes: ['COMPACT_DSL_VALIDATION_FAILED'],
          url: '/validation-1.png',
          alt: '第一次校验',
        },
        {
          label: '执行尝试 1 · 接口调用 2 · 校验评估 1',
          status: '校验通过',
          errorTypes: [],
          error: 'DSL 无法解析',
        },
      ],
    }} />);

    expect(screen.getByRole('img', { name: '第一次校验' })).toHaveAttribute(
      'src',
      '/validation-1.png',
    );
    expect(screen.queryByText('DSL 无法解析')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下一张图片' }));
    expect(screen.getByText('DSL 无法解析')).toBeInTheDocument();
    expect(screen.getByText(/接口调用 2 · 校验评估 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '显示缩略图' }));
    expect(screen.getByRole('button', { name: '查看第 1 张图片' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看第 1 张图片' }));
    expect(screen.getByRole('img', { name: '第一次校验' })).toBeInTheDocument();
  });

  it.each(['browser-capture', 'device-capture'])(
    'renders a single %s image when the manifest uses the gallery renderer',
    (key) => {
      render(<PostprocessArtifactView artifact={{
        key, title: '卡片截图', dataType: 'image', renderer: 'gallery',
        url: `/assets/${key}/Q001.png`, alt: 'Q001 截图', fullUrl: '/assets/full.png',
      }} />);
      expect(screen.getByRole('img', { name: 'Q001 截图' })).toHaveAttribute(
        'src', `/assets/${key}/Q001.png`,
      );
      expect(screen.getByRole('link', { name: '查看原图 ↗' })).toHaveAttribute('href', '/assets/full.png');
      expect(screen.queryByText('暂无图片')).not.toBeInTheDocument();
    },
  );

  it('keeps gallery collections ahead of a fallback URL and handles empty collections', () => {
    const { rerender } = render(<PostprocessArtifactView artifact={{
      key: 'images', dataType: 'image', renderer: 'gallery', url: '/fallback.png',
      data: [{ url: '/first.png', alt: '列表图片' }],
    }} />);
    expect(screen.getByRole('img', { name: '列表图片' })).toHaveAttribute('src', '/first.png');
    rerender(<PostprocessArtifactView artifact={{
      key: 'images', dataType: 'image', renderer: 'gallery', data: [],
    }} />);
    expect(screen.getByText('暂无图片')).toBeInTheDocument();
  });

  it('renders DSL items when a finalized image is not available yet', async () => {
    render(<PostprocessArtifactView artifact={{
      key: 'validation-renders',
      title: '收尾中的 DSL',
      dataType: 'image',
      renderer: 'gallery',
      data: [{
        label: '校验评估 1',
        status: '校验失败',
        size: '2x2',
        dsl: [
          '{"version":"v0.9","createSurface":{"surfaceId":"preview"}}',
          '{"version":"v0.9","updateComponents":{"surfaceId":"preview","root":"root","components":[{"id":"root","component":"Text","content":"DSL 预览"}]}}',
        ].join('\n'),
      }],
    }} />);

    expect(await screen.findByText('DSL 预览')).toBeInTheDocument();
  });

  it('converts Compact gallery items through Python before showing them', async () => {
    const source = '["root","PillButton",{"label":"后处理"}]';
    const genui = [
      '{"version":"v0.9","createSurface":{"surfaceId":"preview"}}',
      '{"version":"v0.9","updateComponents":{"surfaceId":"preview","root":"root","components":[{"id":"root","component":"Text","content":"Python 画廊"}]}}',
    ].join('\n');
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ genui, size: '2x4' }) });
    vi.stubGlobal('fetch', fetchMock);
    render(<PostprocessArtifactView artifact={{
      key: 'gallery', title: '画廊', dataType: 'image', renderer: 'gallery',
      data: [{ label: 'Compact', dsl: source, size: '2x4', appVersion: '12.0.0.1' }],
    }} />);
    expect(await screen.findByText('Python 画廊')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe('/debug/renderer/convert');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ source, size: '2x4', appVersion: '12.0.0.1' });
  });
});
