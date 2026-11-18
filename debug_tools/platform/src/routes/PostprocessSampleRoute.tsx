import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  getPostprocessDashboard,
  getPostprocessSample,
  type PostprocessDashboard,
  type PostprocessSampleResult,
} from '../batchApi';
import { PostprocessArtifactView } from '../components/PostprocessArtifactView';

export function PostprocessSampleRoute() {
  const { runId = '', executionId = '', pluginId = '', sampleId = '' } = useParams();
  const [dashboard, setDashboard] = useState<PostprocessDashboard | null>(null);
  const [sample, setSample] = useState<PostprocessSampleResult | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const [nextDashboard, nextSample] = await Promise.all([
      getPostprocessDashboard(runId, executionId, pluginId),
      getPostprocessSample(runId, executionId, pluginId, sampleId),
    ]);
    setDashboard(nextDashboard);
    setSample(nextSample);
  }, [executionId, pluginId, runId, sampleId]);

  useEffect(() => {
    document.documentElement.classList.add('postprocess-dashboard-active');
    document.body.classList.add('postprocess-dashboard-active');
    return () => {
      document.documentElement.classList.remove('postprocess-dashboard-active');
      document.body.classList.remove('postprocess-dashboard-active');
    };
  }, []);

  useEffect(() => {
    load().catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [load]);

  if (!dashboard || !sample) {
    return <main className="postprocess-dashboard-page"><div className="batch-empty">
      {error || '正在加载样本明细…'}
    </div></main>;
  }

  const title = dashboard.samples.find((item) => item.sampleId === sampleId)?.title;
  const backPath = `/batch/runs/${encodeURIComponent(runId)}/postprocess/`
    + `${encodeURIComponent(executionId)}/plugins/${encodeURIComponent(pluginId)}`;
  const artifacts = sample.artifacts ?? [];

  return <main className="postprocess-dashboard-page">
    <header className="postprocess-dashboard-header">
      <div>
        <Link to={backPath}>← 返回 {dashboard.plugin.name} 看板</Link>
        <h1>{sampleId}{title ? ` · ${title}` : ''}</h1>
        <p>{sample.summary}</p>
      </div>
    </header>
    {error && <div className="batch-error" role="alert">{error}</div>}
    <section className="postprocess-sample-detail">
      {artifacts.map((artifact) => (
        <PostprocessArtifactView key={artifact.key} artifact={artifact} />
      ))}
      {!artifacts.length && <div className="postprocess-empty">该样本没有可展示明细</div>}
    </section>
  </main>;
}
