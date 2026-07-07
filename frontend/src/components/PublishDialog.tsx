/**
 * 发布对话框组件 —— 选择发布目标 + 发布文章（支持 WordPress / Webhook / 微信公众号）
 */

import { useEffect, useState } from 'react';
import {
  listPublishTargets,
  publishArticle,
  listWechatConfigs,
  publishToWechat,
  type PublishTarget,
  type WechatConfig,
  type WechatPublishResponse,
} from '@/lib/publish-api';

interface PublishDialogProps {
  articleId: string;
  onClose: () => void;
  onSuccess: () => void;
}

type PublishMode = 'wordpress' | 'webhook' | 'wechat';

export function PublishDialog({ articleId, onClose, onSuccess }: PublishDialogProps): JSX.Element {
  // 发布模式
  const [mode, setMode] = useState<PublishMode>('wordpress');

  // WordPress/Webhook 相关状态
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [selectedTargetId, setSelectedTargetId] = useState('');
  const [wpStatus, setWpStatus] = useState('draft');

  // 微信公众号相关状态
  const [wechatConfigs, setWechatConfigs] = useState<WechatConfig[]>([]);
  const [selectedWechatId, setSelectedWechatId] = useState('');
  const [wechatAuthor, setWechatAuthor] = useState('');
  const [wechatDigest, setWechatDigest] = useState('');

  // 通用状态
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [copyContent, setCopyContent] = useState('');

  // 加载数据
  useEffect(() => {
    void loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      // 并行加载发布目标和微信配置
      const [targetsData, wechatData] = await Promise.all([
        listPublishTargets(true),
        listWechatConfigs(),
      ]);

      setTargets(targetsData);
      setWechatConfigs(wechatData);

      // 自动选择第一个目标
      if (targetsData.length > 0 && targetsData[0]) {
        setSelectedTargetId(targetsData[0].id);
      }

      // 自动选择第一个微信配置
      if (wechatData.length > 0 && wechatData[0]) {
        setSelectedWechatId(wechatData[0].id);
      }

      // 如果有微信配置，自动切换到微信模式
      if (wechatData.length > 0 && targetsData.length === 0) {
        setMode('wechat');
      }
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }

  // WordPress/Webhook 发布
  async function handlePublishStandard() {
    if (!selectedTargetId) {
      setError('请选择发布目标');
      return;
    }

    setPublishing(true);
    setError('');
    setSuccessMsg('');

    try {
      const result = await publishArticle(articleId, {
        target_id: selectedTargetId,
        status: wpStatus,
      });

      if (result.success) {
        setSuccessMsg(result.message || '发布成功');
        onSuccess();
        setTimeout(() => onClose(), 1500);
      } else {
        setError(result.message || '发布失败');
      }
    } catch (err: any) {
      setError(err.message || '发布失败');
    } finally {
      setPublishing(false);
    }
  }

  // 微信公众号发布
  async function handlePublishWechat() {
    if (wechatConfigs.length === 0) {
      setError('未配置微信公众号，请先配置');
      return;
    }

    if (!selectedWechatId) {
      setError('请选择要发布的微信公众号');
      return;
    }

    setPublishing(true);
    setError('');
    setSuccessMsg('');
    setCopyContent('');

    try {
      const result: WechatPublishResponse = await publishToWechat({
        article_id: articleId,
        config_id: selectedWechatId,
        author: wechatAuthor || undefined,
        digest: wechatDigest || undefined,
      });

      if (result.success) {
        setSuccessMsg(result.message || '已提交发布');
        onSuccess();

        // 如果有 publish_id，提示用户查看状态
        if (result.publish_id) {
          setSuccessMsg(`${result.message}（发布ID: ${result.publish_id}）`);
        }
      } else if (result.fallback && result.copy_content) {
        // 降级为手动复制
        setCopyContent(result.copy_content);
        setError(result.message || '自动发布失败，请手动复制内容');
      } else {
        setError(result.message || '发布失败');
      }
    } catch (err: any) {
      setError(err.message || '发布失败');
    } finally {
      setPublishing(false);
    }
  }

  // 复制内容到剪贴板
  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(copyContent);
      setSuccessMsg('已复制到剪贴板，请粘贴到微信公众号后台');
    } catch {
      // 降级方案
      const textarea = document.createElement('textarea');
      textarea.value = copyContent;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setSuccessMsg('已复制到剪贴板，请粘贴到微信公众号后台');
    }
  }

  // 动态获取选中的目标/配置
  const selectedTarget = targets.find((t) => t.id === selectedTargetId);
  const selectedWechatConfig = wechatConfigs.find((c) => c.id === selectedWechatId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold text-slate-800">发布文章</h2>

        {/* 发布模式选择 */}
        <div className="mb-4 flex rounded-lg border border-slate-200 p-1">
          <button
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              mode === 'wordpress'
                ? 'bg-slate-800 text-white'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
            onClick={() => setMode('wordpress')}
          >
            WordPress / Webhook
          </button>
          <button
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              mode === 'wechat'
                ? 'bg-green-600 text-white'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
            onClick={() => setMode('wechat')}
          >
            微信公众号
          </button>
        </div>

        {/* 错误和成功消息 */}
        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {successMsg && (
          <div className="mb-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-700">
            {successMsg}
          </div>
        )}

        {loading ? (
          <div className="py-8 text-center text-sm text-slate-500">加载中...</div>
        ) : (
          <>
            {/* WordPress/Webhook 模式 */}
            {mode === 'wordpress' && (
              <div className="space-y-4">
                {targets.length === 0 ? (
                  <div className="py-8 text-center">
                    <p className="mb-4 text-sm text-slate-500">暂无发布目标</p>
                    <p className="text-xs text-slate-400">
                      请先在设置页面配置发布目标（WordPress / Webhook）
                    </p>
                  </div>
                ) : (
                  <>
                    {/* 选择发布目标 */}
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">发布目标</label>
                      <select
                        className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                        value={selectedTargetId}
                        onChange={(e) => setSelectedTargetId(e.target.value)}
                      >
                        {targets.map((target) => (
                          <option key={target.id} value={target.id}>
                            {target.name} ({target.type})
                          </option>
                        ))}
                      </select>
                      {selectedTarget && (
                        <p className="mt-1 text-xs text-slate-500">
                          {selectedTarget.type === 'wordpress'
                            ? `WordPress: ${selectedTarget.config.site_url || '未配置'}`
                            : `Webhook: ${selectedTarget.config.webhook_url || '未配置'}`}
                        </p>
                      )}
                    </div>

                    {/* WordPress 状态选择 */}
                    {selectedTarget?.type === 'wordpress' && (
                      <div>
                        <label className="mb-2 block text-sm font-medium text-slate-700">发布状态</label>
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

                    {/* 发布按钮 */}
                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                        onClick={onClose}
                        disabled={publishing}
                      >
                        取消
                      </button>
                      <button
                        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                        onClick={() => void handlePublishStandard()}
                        disabled={publishing || targets.length === 0}
                      >
                        {publishing ? '发布中...' : '🚀 发布'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* 微信公众号模式 */}
            {mode === 'wechat' && (
              <div className="space-y-4">
                {wechatConfigs.length === 0 ? (
                  <div className="py-8 text-center">
                    <div className="mb-4 text-4xl">📱</div>
                    <p className="mb-2 text-sm text-slate-600">暂未配置微信公众号</p>
                    <p className="text-xs text-slate-400">
                      请先在「发布目标管理 → 微信公众号配置」中添加
                    </p>
                  </div>
                ) : (
                  <>
                    {/* 选择微信公众号配置 */}
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        选择公众号
                      </label>
                      <select
                        className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-green-500 focus:outline-none"
                        value={selectedWechatId}
                        onChange={(e) => setSelectedWechatId(e.target.value)}
                      >
                        {wechatConfigs.map((config) => (
                          <option key={config.id} value={config.id}>
                            {config.name}
                          </option>
                        ))}
                      </select>
                      {selectedWechatConfig && (
                        <p className="mt-1 text-xs text-slate-500">
                          AppID: {selectedWechatConfig.app_id}
                        </p>
                      )}
                    </div>

                    {/* 作者 */}
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        作者（可选）
                      </label>
                      <input
                        type="text"
                        className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-green-500 focus:outline-none"
                        placeholder="留空使用默认作者"
                        value={wechatAuthor}
                        onChange={(e) => setWechatAuthor(e.target.value)}
                      />
                    </div>

                    {/* 摘要 */}
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        摘要（可选，最多 120 字）
                      </label>
                      <textarea
                        className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-green-500 focus:outline-none"
                        rows={2}
                        placeholder="留空使用文章摘要"
                        value={wechatDigest}
                        onChange={(e) => setWechatDigest(e.target.value)}
                        maxLength={120}
                      />
                      <p className="mt-1 text-xs text-slate-400">
                        {wechatDigest.length}/120
                      </p>
                    </div>

                    {/* 复制内容显示 */}
                    {copyContent && (
                      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                        <div className="mb-2 flex items-center justify-between">
                          <span className="text-sm font-medium text-amber-800">
                            手动发布内容
                          </span>
                          <button
                            className="rounded bg-amber-600 px-3 py-1 text-xs text-white hover:bg-amber-700"
                            onClick={() => void handleCopy()}
                          >
                            📋 复制
                          </button>
                        </div>
                        <textarea
                          className="w-full rounded border border-amber-300 bg-white px-3 py-2 text-sm font-mono"
                          rows={8}
                          value={copyContent}
                          readOnly
                        />
                        <p className="mt-2 text-xs text-amber-600">
                          复制上方内容，打开微信公众号后台 → 新建图文 → 粘贴发布
                        </p>
                      </div>
                    )}

                    {/* 发布按钮 */}
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
                        onClick={() => void handlePublishWechat()}
                        disabled={publishing}
                      >
                        {publishing ? '发布中...' : '📱 发布到微信'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
