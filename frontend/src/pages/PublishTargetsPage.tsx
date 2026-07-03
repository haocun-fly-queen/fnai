/**
 * 发布目标管理页面（阶段 5）—— 配置 WordPress / Webhook 发布目标
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listPublishTargets,
  createPublishTarget,
  updatePublishTarget,
  deletePublishTarget,
  type PublishTarget,
  type PublishTargetCreate,
} from '@/lib/publish-api';

export function PublishTargetsPage(): JSX.Element {
  const navigate = useNavigate();
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  useEffect(() => {
    void loadTargets();
  }, []);

  async function loadTargets() {
    setLoading(true);
    try {
      const data = await listPublishTargets(false); // 包括禁用的
      setTargets(data);
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`确定删除发布目标"${name}"吗？`)) return;

    try {
      await deletePublishTarget(id);
      await loadTargets();
    } catch (err: any) {
      alert(err.message || '删除失败');
    }
  }

  async function handleToggleActive(target: PublishTarget) {
    try {
      await updatePublishTarget(target.id, { is_active: !target.is_active });
      await loadTargets();
    } catch (err: any) {
      alert(err.message || '更新失败');
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <button
              className="text-sm text-slate-500 hover:text-slate-800"
              onClick={() => navigate('/articles')}
            >
              ← 返回
            </button>
            <span className="text-sm text-slate-300">|</span>
            <h1 className="text-lg font-semibold text-slate-800">发布目标管理</h1>
          </div>
          <div className="flex items-center gap-3">
            <button
              className="rounded border border-green-300 px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-50"
              onClick={() => navigate('/wechat-config')}
            >
              📱 微信公众号配置
            </button>
            <button
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              onClick={() => setShowCreateDialog(true)}
            >
              ➕ 新建目标
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-12 text-center text-sm text-slate-500">加载中...</div>
        ) : targets.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-white p-12 text-center">
            <p className="mb-2 text-sm text-slate-600">暂无发布目标</p>
            <p className="text-xs text-slate-400">点击右上角"新建目标"按钮创建 WordPress 或 Webhook 发布目标</p>
          </div>
        ) : (
          <div className="space-y-4">
            {targets.map((target) => (
              <div key={target.id} className="rounded-lg border border-slate-200 bg-white p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-semibold text-slate-800">{target.name}</h3>
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${
                          target.type === 'wordpress'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-purple-100 text-purple-700'
                        }`}
                      >
                        {target.type}
                      </span>
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${
                          target.is_active
                            ? 'bg-green-100 text-green-700'
                            : 'bg-slate-100 text-slate-500'
                        }`}
                      >
                        {target.is_active ? '启用' : '禁用'}
                      </span>
                    </div>

                    <div className="mt-3 space-y-1 text-sm text-slate-600">
                      {target.type === 'wordpress' && (
                        <>
                          <div>
                            <span className="font-medium">站点：</span>
                            {target.config.site_url || '未配置'}
                          </div>
                          <div>
                            <span className="font-medium">用户名：</span>
                            {target.config.username || '未配置'}
                          </div>
                        </>
                      )}
                      {target.type === 'webhook' && (
                        <div>
                          <span className="font-medium">URL：</span>
                          {target.config.webhook_url || '未配置'}
                        </div>
                      )}
                    </div>

                    <div className="mt-2 text-xs text-slate-400">
                      创建于 {new Date(target.created_at).toLocaleString('zh-CN')}
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                      onClick={() => void handleToggleActive(target)}
                    >
                      {target.is_active ? '禁用' : '启用'}
                    </button>
                    <button
                      className="rounded border border-red-300 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50"
                      onClick={() => void handleDelete(target.id, target.name)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreateDialog && (
        <CreateTargetDialog
          onClose={() => setShowCreateDialog(false)}
          onSuccess={() => {
            setShowCreateDialog(false);
            void loadTargets();
          }}
        />
      )}
    </div>
  );
}

// ---- 创建目标对话框 ----

interface CreateTargetDialogProps {
  onClose: () => void;
  onSuccess: () => void;
}

function CreateTargetDialog({ onClose, onSuccess }: CreateTargetDialogProps): JSX.Element {
  const [type, setType] = useState<'wordpress' | 'webhook'>('wordpress');
  const [name, setName] = useState('');
  const [config, setConfig] = useState<Record<string, string>>({
    site_url: '',
    username: '',
    app_password: '',
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  function updateConfig(key: string, value: string) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCreate() {
    if (!name.trim()) {
      setError('请输入目标名称');
      return;
    }

    if (type === 'wordpress') {
      if (!config.site_url || !config.username || !config.app_password) {
        setError('请完整填写 WordPress 配置');
        return;
      }
    } else {
      if (!config.webhook_url) {
        setError('请填写 Webhook URL');
        return;
      }
    }

    setCreating(true);
    setError('');

    try {
      const data: PublishTargetCreate = {
        name: name.trim(),
        type,
        config,
        is_active: true,
      };
      await createPublishTarget(data);
      onSuccess();
    } catch (err: any) {
      setError(err.message || '创建失败');
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold text-slate-800">新建发布目标</h2>

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* 目标名称 */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">目标名称</label>
            <input
              type="text"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="如：公司官网"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* 类型选择 */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">类型</label>
            <select
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              value={type}
              onChange={(e) => {
                const newType = e.target.value as 'wordpress' | 'webhook';
                setType(newType);
                setConfig(
                  newType === 'wordpress'
                    ? { site_url: '', username: '', app_password: '' }
                    : { webhook_url: '', headers: '{}' }
                );
              }}
            >
              <option value="wordpress">WordPress</option>
              <option value="webhook">Webhook</option>
            </select>
          </div>

          {/* WordPress 配置 */}
          {type === 'wordpress' && (
            <>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">站点 URL</label>
                <input
                  type="url"
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  placeholder="https://example.com"
                  value={config.site_url || ''}
                  onChange={(e) => updateConfig('site_url', e.target.value)}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">用户名</label>
                <input
                  type="text"
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  placeholder="WordPress 用户名"
                  value={config.username || ''}
                  onChange={(e) => updateConfig('username', e.target.value)}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">
                  Application Password
                </label>
                <input
                  type="password"
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
                  value={config.app_password || ''}
                  onChange={(e) => updateConfig('app_password', e.target.value)}
                />
                <p className="mt-1 text-xs text-slate-500">
                  在 WordPress 后台"用户 → 个人资料"中生成
                </p>
              </div>
            </>
          )}

          {/* Webhook 配置 */}
          {type === 'webhook' && (
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">Webhook URL</label>
              <input
                type="url"
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                placeholder="https://api.example.com/publish"
                value={config.webhook_url || ''}
                onChange={(e) => updateConfig('webhook_url', e.target.value)}
              />
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex justify-end gap-2 pt-2">
            <button
              className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              onClick={onClose}
              disabled={creating}
            >
              取消
            </button>
            <button
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              onClick={() => void handleCreate()}
              disabled={creating}
            >
              {creating ? '创建中...' : '创建'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
