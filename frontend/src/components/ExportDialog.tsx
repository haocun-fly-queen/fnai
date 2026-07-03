/**
 * 导出对话框组件 —— Markdown / HTML 导出
 */

import { useState } from 'react';
import { exportArticle } from '@/lib/publish-api';

interface ExportDialogProps {
  articleId: string;
  articleTitle: string;
  onClose: () => void;
}

export function ExportDialog({ articleId, articleTitle, onClose }: ExportDialogProps): JSX.Element {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  async function handleExport(format: 'markdown' | 'html') {
    setExporting(true);
    setError('');

    try {
      const blob = await exportArticle(articleId, format);

      // 触发浏览器下载
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${articleTitle}.${format === 'markdown' ? 'md' : 'html'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      onClose();
    } catch (err: any) {
      setError(err.message || '导出失败');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold text-slate-800">导出文章</h2>

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="mb-6 space-y-3">
          <button
            className="w-full rounded border border-slate-300 bg-white px-4 py-3 text-left text-sm hover:bg-slate-50 disabled:opacity-50"
            onClick={() => handleExport('markdown')}
            disabled={exporting}
          >
            <div className="font-medium text-slate-800">📝 Markdown</div>
            <div className="mt-1 text-xs text-slate-500">适合 GitHub、Notion 等平台</div>
          </button>

          <button
            className="w-full rounded border border-slate-300 bg-white px-4 py-3 text-left text-sm hover:bg-slate-50 disabled:opacity-50"
            onClick={() => handleExport('html')}
            disabled={exporting}
          >
            <div className="font-medium text-slate-800">🌐 HTML</div>
            <div className="mt-1 text-xs text-slate-500">完整 HTML 文档（带样式）</div>
          </button>
        </div>

        <div className="flex justify-end">
          <button
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
            onClick={onClose}
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
