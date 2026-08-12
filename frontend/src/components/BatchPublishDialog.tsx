/**
 * 批量发布对话框 —— 把选中的多篇文章发布到一个或多个目标。
 *
 * 后端为每个 (文章 × 目标) 组合投递一个 Celery 任务，本对话框提交后即结束；
 * 各文章的发布结果需到文章编辑器的发布历史里查看。
 */

import { useEffect, useState } from 'react';
import {
  listPublishTargets,
  batchPublish,
  type PublishTarget,
} from '@/lib/publish-api';

interface BatchPublishDialogProps {
  articleIds: string[];
  onClose: () => void;
  onSuccess: (message: string) => void;
}

export function BatchPublishDialog({
  articleIds,
  onClose,
  onSuccess,
}: BatchPublishDialogProps): JSX.Element {
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [selectedTargetIds, setSelectedTargetIds] = useState<Set<string>>(new Set());
  const [wpStatus, setWpStatus] = useState('draft');

  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void loadData();
  }, []);

  async function loadData(): Promise<void> {
    setLoading(true);
    setError('');
    try {
      const data = await listPublishTargets(true);
      setTargets(data);
    } catch (e) {
      setError(`加载发布目标失败: ${(e as { message?: string }).message ?? e}`);
    } finally {
      setLoading(false);
    }
  }

  function toggleTarget(id: string): void {
    setSelectedTargetIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // 只要选中的目标里有 WordPress，就显示状态选择器
  const anyWordpressSelected = targets.some(
    (t) => t.type === 'wordpress' && selectedTargetIds.has(t.id),
  );

  async function handlePublish(): Promise<void> {
    if (selectedTargetIds.size === 0) {
      setError('请至少选择一个发布目标');
      return;
    }
    setPublishing(true);
    setError('');
    try {
      const res = await batchPublish({
        article_ids: articleIds,
        target_ids: Array.from(selectedTargetIds),
        status: wpStatus,
      });
      onSuccess(res.message);
      onClose();
    } catch (e) {
      setError(`批量发布失败: ${(e as { message?: string }).message ?? e}`);
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-1 text-lg font-semibold text-slate-800">批量发布</h2>
        <p className="mb-4 text-sm text-slate-500">
          已选 {articleIds.length} 篇文章，将发布到选中的每个目标。
        </p>

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-8 text-center text-sm text-slate-500">加载中...</div>
        ) : targets.length === 0 ? (
          <div className="py-8 text-center">
            <p className="mb-2 text-sm text-slate-500">暂无发布目标</p>
            <p className="text-xs text-slate-400">
              请先在设置页面配置发布目标（WordPress / Webhook）
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* 选择发布目标（多选） */}
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">
                发布目标（可多选）
              </label>
              <div className="max-h-48 space-y-1 overflow-y-auto rounded border border-slate-200 p-2">
                {targets.map((target) => (
                  <label
                    key={target.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedTargetIds.has(target.id)}
                      onChange={() => toggleTarget(target.id)}
                    />
                    <span className="text-slate-800">{target.name}</span>
                    <span className="text-xs text-slate-400">({target.type})</span>
                  </label>
                ))}
              </div>
            </div>

            {/* WordPress 状态选择 */}
            {anyWordpressSelected && (
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">
                  WordPress 发布状态
                </label>
                <select
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  value={wpStatus}
                  onChange={(e) => setWpStatus(e.target.value)}
                >
                  <option value="draft">草稿</option>
                  <option value="publish">立即发布</option>
                </select>
              </div>
            )}

            {/* 操作按钮 */}
            <div className="flex justify-end gap-2 pt-2">
              <button
                className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                onClick={onClose}
                disabled={publishing}
              >
                取消
              </button>
              <button
                className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                onClick={() => void handlePublish()}
                disabled={publishing || selectedTargetIds.size === 0}
              >
                {publishing ? '提交中...' : `🚀 发布到 ${selectedTargetIds.size} 个目标`}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
