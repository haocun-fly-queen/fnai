/**
 * 微博配置页面（阶段 5）—— 管理微博账号配置
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listWeiboConfigs,
  createWeiboConfig,
  deleteWeiboConfig,
  verifyWeiboCookie,
  type WeiboConfig,
  type WeiboConfigCreate,
} from '@/lib/publish-api';

export function WeiboConfigPage(): JSX.Element {
  const navigate = useNavigate();
  const [configs, setConfigs] = useState<WeiboConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  useEffect(() => {
    void loadConfigs();
  }, []);

  async function loadConfigs() {
    setLoading(true);
    try {
      const data = await listWeiboConfigs();
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
      await deleteWeiboConfig(id);
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
            <h1 className="text-lg font-semibold text-slate-800">微博账号配置</h1>
          </div>
          <button
            className="rounded bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700"
            onClick={() => setShowCreateDialog(true)}
          >
            ➕ 添加微博号
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
        <div className="mb-6 rounded-lg border border-orange-200 bg-orange-50 p-4">
          <h3 className="mb-2 text-sm font-semibold text-orange-800">配置说明</h3>
          <ul className="space-y-1 text-xs text-orange-700">
            <li>• 通过微博 Cookie 方式发布，无需申请开发者账号</li>
            <li>• 获取 Cookie：打开 m.weibo.cn → 登录 → F12 开发者工具 → Network → 复制 Cookie</li>
            <li>• Cookie 有效期较长，但修改密码后会失效</li>
            <li>• 发布内容为微博正文，支持配图</li>
          </ul>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-slate-500">加载中...</div>
        ) : configs.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-white p-12 text-center">
            <div className="mb-4 text-4xl">📢</div>
            <p className="mb-2 text-sm text-slate-600">暂未配置微博账号</p>
            <p className="text-xs text-slate-400">
              点击右上角「添加微博号」按钮配置你的微博账号
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
                        <span className="font-medium">Cookie：</span>
                        <span className="font-mono text-xs">{config.cookie_preview || '***'}</span>
                      </div>
                      {config.default_suffix && (
                        <div>
                          <span className="font-medium">默认尾部内容：</span>
                          {config.default_suffix}
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
  const [cookie, setCookie] = useState('');
  const [defaultSuffix, setDefaultSuffix] = useState('');
  const [creating, setCreating] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState('');
  const [error, setError] = useState('');

  // 自动获取 Cookie 相关状态
  const [autoGetting, setAutoGetting] = useState(false);
  const [autoStatus, setAutoStatus] = useState('');
  // 用 127.0.0.1 而不是 localhost：Windows 上 localhost 常优先解析为 IPv6 (::1)，
  // 而本地取 Cookie 服务只监听 IPv4，会导致 ERR_CONNECTION_REFUSED。
  const LOCAL_SERVICE = 'http://127.0.0.1:5001';

  // 自动获取 Cookie
  async function handleAutoGetCookie() {
    setAutoGetting(true);
    setAutoStatus('正在连接本地服务...');
    setError('');

    try {
      // 1. 调用本地服务，打开浏览器
      const startRes = await fetch(`${LOCAL_SERVICE}/get-cookie`);
      const startData = await startRes.json();

      if (startData.error) {
        setAutoStatus(`❌ ${startData.error}`);
        setAutoGetting(false);
        return;
      }

      setAutoStatus('🌐 浏览器已打开，请登录微博...');

      // 2. 轮询检查结果
      const poll = async (): Promise<void> => {
        const checkRes = await fetch(`${LOCAL_SERVICE}/check-cookie`);
        const checkData = await checkRes.json();

        if (checkData.status === 'pending') {
          // 还在等待登录
          setAutoStatus('🌐 浏览器已打开，请登录微博...');
          await new Promise(r => setTimeout(r, 2000));
          await poll();
        } else if (checkData.status === 'success') {
          // 获取成功
          setCookie(checkData.cookie);
          setAutoStatus('✅ Cookie 获取成功！已自动填入');
          setAutoGetting(false);
        } else if (checkData.status === 'failed') {
          setAutoStatus(`❌ ${checkData.error}`);
          setAutoGetting(false);
        } else {
          setAutoStatus('');
          setAutoGetting(false);
        }
      };

      await new Promise(r => setTimeout(r, 1000));
      await poll();
    } catch (err: any) {
      setError('本地服务未启动，请先运行 weibo_cookie_service.py');
      setAutoGetting(false);
      setAutoStatus('');
    }
  }

  async function handleVerify() {
    if (!cookie.trim()) {
      setError('请先输入 Cookie');
      return;
    }

    setVerifying(true);
    setVerifyResult('');
    setError('');

    try {
      const result = await verifyWeiboCookie(cookie.trim());
      if (result.valid && result.user) {
        setVerifyResult(`✅ Cookie 有效！用户：${result.user.screen_name}（粉丝：${result.user.followers_count}）`);
      } else {
        setVerifyResult(`❌ ${result.message || 'Cookie 无效'}`);
      }
    } catch (err: any) {
      setVerifyResult(`❌ 验证失败：${err.message || '网络错误'}`);
    } finally {
      setVerifying(false);
    }
  }

  async function handleCreate() {
    if (!name.trim()) {
      setError('请输入配置名称');
      return;
    }
    if (!cookie.trim()) {
      setError('请输入 Cookie');
      return;
    }

    setCreating(true);
    setError('');

    try {
      const data: WeiboConfigCreate = {
        name: name.trim(),
        cookie: cookie.trim(),
        default_suffix: defaultSuffix.trim() || undefined,
      };
      await createWeiboConfig(data);
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
        <h2 className="mb-4 text-lg font-semibold text-slate-800">添加微博账号</h2>

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
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
              placeholder="如：公司微博号"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Cookie */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">微博 Cookie</label>
            <textarea
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm font-mono focus:border-orange-500 focus:outline-none"
              placeholder="粘贴从 m.weibo.cn 开发者工具获取的 Cookie"
              rows={3}
              value={cookie}
              onChange={(e) => setCookie(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              打开 m.weibo.cn → 登录 → F12 → Network → 复制任意请求的 Cookie
            </p>
          </div>

          {/* 自动获取 Cookie */}
          <div>
            <button
              className="rounded border border-blue-300 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-100 disabled:opacity-50"
              onClick={() => void handleAutoGetCookie()}
              disabled={autoGetting}
            >
              {autoGetting ? '⏳ 获取中...' : '🤖 自动获取 Cookie'}
            </button>
            {autoStatus && (
              <p className="mt-2 text-xs text-slate-600">{autoStatus}</p>
            )}
            {!autoGetting && !autoStatus && (
              <p className="mt-1 text-xs text-slate-400">
                点击后会自动打开浏览器，登录微博后自动获取 Cookie
              </p>
            )}
          </div>

          {/* 验证按钮 - 暂时隐藏 */}
          <div className="hidden">
            <button
              className="rounded border border-orange-300 px-3 py-1.5 text-xs text-orange-600 hover:bg-orange-50 disabled:opacity-50"
              onClick={() => void handleVerify()}
              disabled={verifying}
            >
              {verifying ? '验证中...' : '🔍 验证 Cookie'}
            </button>
            {verifyResult && (
              <p className="mt-2 text-xs text-slate-600">{verifyResult}</p>
            )}
          </div>

          {/* 默认尾部内容 */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">
              默认尾部内容（可选）
            </label>
            <input
              type="text"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
              placeholder="如：#医药健康# 详情请看→"
              value={defaultSuffix}
              onChange={(e) => setDefaultSuffix(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              发布微博时会自动追加在内容末尾
            </p>
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
              className="rounded bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50"
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
