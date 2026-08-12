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
        // 只保留最新的一条记录
        setLogs(result.slice(0, 1));
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
        {logs.map((log, index) => (
          <PublishLogItem key={`${log.target_name}-${log.published_at}-${index}`} log={log} />
        ))}
      </div>
    </div>
  );
}

function PublishLogItem({ log }: { log: PublishLog }) {
  // 根据 is_published 确定状态
  const config = log.is_published
    ? { label: '已发布', color: 'bg-green-500', textColor: 'text-green-700' }
    : { label: '未发布', color: 'bg-slate-400', textColor: 'text-slate-700' };

  // 格式化时间（精确到秒）
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);

    // 检查时间是否有效
    if (isNaN(date.getTime())) {
      return '无效时间';
    }

    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: 'Asia/Shanghai', // 明确指定中国时区
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
      </div>

      {/* 平台名称 */}
      <div className="mb-2 space-y-1">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">目标:</span>
          <span className="font-medium text-slate-700">{log.target_name}</span>
        </div>
      </div>

      {/* 时间信息 */}
      <div className="space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-500">
        <div className="flex justify-between">
          <span>{log.is_published ? '发布时间:' : '最近尝试:'}</span>
          <span className={`font-mono ${log.is_published ? 'text-green-600 font-medium' : ''}`}>
            {formatTime(log.published_at)}
          </span>
        </div>
      </div>
    </div>
  );
}
