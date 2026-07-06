import { useEffect, useState } from 'react';
import { getPublishLogs, type PublishLog } from '@/lib/publish-api';

interface PublishStatusCardProps {
  articleId: string;
}

export function PublishStatusCard({ articleId }: PublishStatusCardProps) {
  const [logs, setLogs] = useState<PublishLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const result = await getPublishLogs(articleId);
        setLogs(result);
      } catch (err) {
        console.error('Failed to load publish logs:', err);
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [articleId]);

  if (loading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">发布状态</h3>
        <p className="text-xs text-slate-400">加载中...</p>
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">发布状态</h3>
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-block h-2 w-2 rounded-full bg-slate-300"></span>
          <span className="text-slate-600">未发布</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-3 text-xs font-semibold uppercase text-slate-500">发布状态</h3>
      <div className="space-y-3">
        {logs.map((log) => (
          <PublishLogItem key={log.id} log={log} />
        ))}
      </div>
    </div>
  );
}

function PublishLogItem({ log }: { log: PublishLog }) {
  const statusConfig = {
    pending: { label: '审核中', color: 'bg-yellow-400', textColor: 'text-yellow-700' },
    success: { label: '已发布', color: 'bg-green-500', textColor: 'text-green-700' },
    failed: { label: '发布失败', color: 'bg-red-500', textColor: 'text-red-700' },
  };

  const config = statusConfig[log.status] || statusConfig.pending;

  // 格式化时间（精确到秒）
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      {/* 状态行 */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2 w-2 rounded-full ${config.color}`}></span>
          <span className={`text-sm font-medium ${config.textColor}`}>{config.label}</span>
        </div>
        {log.remote_id && (
          <span className="text-xs text-slate-400" title="发布任务 ID">
            #{log.remote_id}
          </span>
        )}
      </div>

      {/* 平台名称 */}
      <div className="mb-2 space-y-1">
        {log.target_name && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-500">目标:</span>
            <span className="font-medium text-slate-700">{log.target_name}</span>
          </div>
        )}
      </div>

      {/* 时间信息 */}
      <div className="space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-500">
        {log.published_at && (
          <div className="flex justify-between">
            <span>{log.status === 'success' ? '发布时间:' : '提交时间:'}</span>
            <span className={`font-mono ${log.status === 'success' ? 'text-green-600 font-medium' : ''}`}>
              {formatTime(log.published_at)}
            </span>
          </div>
        )}
      </div>

      {/* 错误信息 */}
      {log.status === 'failed' && log.error_message && (
        <div className="mt-2 rounded bg-red-50 p-2 text-xs text-red-600">
          <span className="font-medium">失败原因: </span>
          {log.error_message}
        </div>
      )}
    </div>
  );
}
