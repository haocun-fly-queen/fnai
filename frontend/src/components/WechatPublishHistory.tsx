import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface PublishHistoryItem {
  id: string;
  publish_id: string | null;
  status: 'pending' | 'success' | 'failed';
  published_at: string;
  error_message: string | null;
  article_url: string | null;
}

interface PublishHistoryResponse {
  total: number;
  items: PublishHistoryItem[];
}

interface WechatPublishHistoryProps {
  articleId: string;
}

export const WechatPublishHistory: React.FC<WechatPublishHistoryProps> = ({ articleId }) => {
  const [history, setHistory] = useState<PublishHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory();
  }, [articleId]);

  const fetchHistory = async () => {
    try {
      setLoading(true);
      const response = await axios.get(
        `/api/v1/wechat/articles/${articleId}/publish-history`
      );
      setHistory(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || '获取发布历史失败');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('链接已复制到剪贴板');
  };

  const formatDateTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'success':
        return <span className="badge badge-success">✅ 成功</span>;
      case 'pending':
        return <span className="badge badge-warning">⏳ 处理中</span>;
      case 'failed':
        return <span className="badge badge-error">❌ 失败</span>;
      default:
        return <span className="badge">{status}</span>;
    }
  };

  if (loading) {
    return (
      <div className="wechat-publish-history">
        <h3>微信发布历史</h3>
        <div className="loading">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="wechat-publish-history">
        <h3>微信发布历史</h3>
        <div className="error">{error}</div>
      </div>
    );
  }

  if (!history || history.total === 0) {
    return (
      <div className="wechat-publish-history">
        <h3>微信发布历史</h3>
        <div className="empty">暂无发布记录</div>
      </div>
    );
  }

  return (
    <div className="wechat-publish-history">
      <div className="header">
        <h3>微信发布历史</h3>
        <button onClick={fetchHistory} className="btn-refresh">
          🔄 刷新
        </button>
      </div>

      <div className="history-list">
        <table>
          <thead>
            <tr>
              <th>发布时间</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {history.items.map((item) => (
              <tr key={item.id}>
                <td>{formatDateTime(item.published_at)}</td>
                <td>{getStatusBadge(item.status)}</td>
                <td>
                  {item.status === 'success' && item.article_url ? (
                    <div className="actions">
                      <button
                        onClick={() => copyToClipboard(item.article_url!)}
                        className="btn btn-sm btn-primary"
                      >
                        📋 复制链接
                      </button>
                      <button
                        onClick={() => window.open(item.article_url!, '_blank')}
                        className="btn btn-sm btn-secondary"
                      >
                        🔗 预览
                      </button>
                    </div>
                  ) : item.status === 'failed' && item.error_message ? (
                    <button
                      onClick={() => alert(item.error_message)}
                      className="btn btn-sm btn-error"
                    >
                      查看错误
                    </button>
                  ) : item.status === 'pending' ? (
                    <span className="text-muted">等待完成...</span>
                  ) : (
                    <span className="text-muted">-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <style>{`
        .wechat-publish-history {
          margin-top: 2rem;
          padding: 1.5rem;
          background: #f9fafb;
          border-radius: 8px;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }

        h3 {
          margin: 0;
          font-size: 1.25rem;
          font-weight: 600;
        }

        .btn-refresh {
          padding: 0.5rem 1rem;
          background: #fff;
          border: 1px solid #e5e7eb;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.875rem;
        }

        .btn-refresh:hover {
          background: #f3f4f6;
        }

        .loading,
        .error,
        .empty {
          padding: 2rem;
          text-align: center;
          color: #6b7280;
        }

        .error {
          color: #ef4444;
        }

        table {
          width: 100%;
          background: white;
          border-radius: 8px;
          overflow: hidden;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        thead {
          background: #f3f4f6;
        }

        th {
          padding: 0.75rem 1rem;
          text-align: left;
          font-weight: 600;
          font-size: 0.875rem;
          color: #374151;
        }

        td {
          padding: 1rem;
          border-top: 1px solid #e5e7eb;
        }

        .badge {
          display: inline-block;
          padding: 0.25rem 0.75rem;
          border-radius: 9999px;
          font-size: 0.875rem;
          font-weight: 500;
        }

        .badge-success {
          background: #d1fae5;
          color: #065f46;
        }

        .badge-warning {
          background: #fef3c7;
          color: #92400e;
        }

        .badge-error {
          background: #fee2e2;
          color: #991b1b;
        }

        .actions {
          display: flex;
          gap: 0.5rem;
        }

        .btn {
          padding: 0.5rem 1rem;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.875rem;
          transition: all 0.2s;
        }

        .btn-sm {
          padding: 0.375rem 0.75rem;
          font-size: 0.8125rem;
        }

        .btn-primary {
          background: #3b82f6;
          color: white;
        }

        .btn-primary:hover {
          background: #2563eb;
        }

        .btn-secondary {
          background: #6b7280;
          color: white;
        }

        .btn-secondary:hover {
          background: #4b5563;
        }

        .btn-error {
          background: #ef4444;
          color: white;
        }

        .btn-error:hover {
          background: #dc2626;
        }

        .text-muted {
          color: #9ca3af;
        }
      `}</style>
    </div>
  );
};
