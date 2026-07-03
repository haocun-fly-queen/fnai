/**
 * 微信公众号配置页面（阶段 5）—— 管理微信公众号配置
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listWechatConfigs,
  createWechatConfig,
  deleteWechatConfig,
  type WechatConfig,
  type WechatConfigCreate,
} from '@/lib/publish-api';

export function WechatConfigPage(): JSX.Element {
  const navigate = useNavigate();
  const [configs, setConfigs] = useState<WechatConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  useEffect(() => {
    void loadConfigs();
  }, []);

  async function loadConfigs() {
    setLoading(true);
    try {
      const data = await listWechatConfigs();
      setConfigs(data);
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`确定删除配置"${name}"吗？`)) return;

    try {
      await deleteWechatConfig(id);
      await loadConfigs();
    } catch (err: any) {
      alert(err.message || '删除失败');
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <button
              className="text-sm text-slate-500 hover:text-slate-800"
              onClick={() => navigate('/publish-targets')}
            >
              ← 返回发布目标
            </button>
            <span className="text-sm text-slate-300">|</span>
            <h1 className="text-lg font-semibold text-slate-800">微信公众号配置</h1>
          </div>
          <button
            className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
            onClick={() => setShowCreateDialog(true)}
          >
            ➕ 添加公众号
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* 使用说明 */}
        <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <h3 className="mb-2 text-sm font-semibold text-blue-800">配置说明</h3>
          <ul className="space-y-1 text-xs text-blue-700">
            <li>• 每个租户只能配置一个微信公众号</li>
            <li>• AppID 和 AppSecret 在微信公众平台「开发 → 基本配置」中获取</li>
            <li>• 需要认证服务号才能使用发布接口</li>
            <li>• 发布后文章会进入草稿箱，需要手动确认发布</li>
          </ul>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-slate-500">加载中...</div>
        ) : configs.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-white p-12 text-center">
            <div className="mb-4 text-4xl">📱</div>
            <p className="mb-2 text-sm text-slate-600">暂未配置微信公众号</p>
            <p className="text-xs text-slate-400">
              点击右上角「添加公众号」按钮配置你的微信公众号
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {configs.map((config) => (
              <div key={config.id} className="rounded-lg border border-slate-200 bg-white p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-semibold text-slate-800">{config.name}</h3>
                      <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                        已启用
                      </span>
                    </div>

                    <div className="mt-3 space-y-1 text-sm text-slate-600">
                      <div>
                        <span className="font-medium">AppID：</span>
                        <span className="font-mono">{config.app_id}</span>
                      </div>
                      {config.author && (
                        <div>
                          <span className="font-medium">默认作者：</span>
                          {config.author}
                        </div>
                      )}
                    </div>

                    <div className="mt-2 text-xs text-slate-400">
                      创建于 {new Date(config.created_at).toLocaleString('zh-CN')}
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      className="rounded border border-red-300 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50"
                      onClick={() => void handleDelete(config.id, config.name)}
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
        <CreateConfigDialog
          onClose={() => setShowCreateDialog(false)}
          onSuccess={() => {
            setShowCreateDialog(false);
            void loadConfigs();
          }}
        />
      )}
    </div>
  );
}

// ---- 创建配置对话框 ----

interface CreateConfigDialogProps {
  onClose: () => void;
  onSuccess: () => void;
}

function CreateConfigDialog({ onClose, onSuccess }: CreateConfigDialogProps): JSX.Element {
  const [name, setName] = useState('');
  const [appId, setAppId] = useState('');
  const [appSecret, setAppSecret] = useState('');
  const [author, setAuthor] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  async function handleCreate() {
    if (!name.trim()) {
      setError('请输入配置名称');
      return;
    }
    if (!appId.trim()) {
      setError('请输入 AppID');
      return;
    }
    if (!appSecret.trim()) {
      setError('请输入 AppSecret');
      return;
    }

    setCreating(true);
    setError('');

    try {
      const data: WechatConfigCreate = {
        name: name.trim(),
        app_id: appId.trim(),
        app_secret: appSecret.trim(),
        author: author.trim() || undefined,
      };
      await createWechatConfig(data);
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
        <h2 className="mb-4 text-lg font-semibold text-slate-800">添加微信公众号</h2>

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* 配置名称 */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">配置名称</label>
            <input
              type="text"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-green-500 focus:outline-none"
              placeholder="如：公司公众号"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* AppID */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">AppID</label>
            <input
              type="text"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm font-mono focus:border-green-500 focus:outline-none"
              placeholder="wx1234567890abcdef"
              value={appId}
              onChange={(e) => setAppId(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              在微信公众平台「开发 → 基本配置」中获取
            </p>
          </div>

          {/* AppSecret */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">AppSecret</label>
            <input
              type="password"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-green-500 focus:outline-none"
              placeholder="请输入 AppSecret"
              value={appSecret}
              onChange={(e) => setAppSecret(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              在微信公众平台「开发 → 基本配置」中重置获取
            </p>
          </div>

          {/* 默认作者 */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">
              默认作者（可选）
            </label>
            <input
              type="text"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-green-500 focus:outline-none"
              placeholder="如：FNAI"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
            />
          </div>

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
              className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
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
