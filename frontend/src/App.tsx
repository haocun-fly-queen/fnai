import { Navigate, Route, Routes } from 'react-router-dom';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { TeamPage } from '@/pages/TeamPage';
import { AcceptInvitationPage } from '@/pages/AcceptInvitationPage';
import { TestPanelPage } from '@/pages/TestPanelPage';
import { KnowledgePage } from '@/pages/KnowledgePage';
import { ArticlesPage } from '@/pages/ArticlesPage';
import { ArticleEditorPage } from '@/pages/ArticleEditorPage';
import { PublishTargetsPage } from '@/pages/PublishTargetsPage';
import { WechatConfigPage } from '@/pages/WechatConfigPage';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { useAuthStore } from '@/stores/auth';

export function App(): JSX.Element {
  const accessToken = useAuthStore((s) => s.accessToken);

  return (
    <Routes>
      <Route
        path="/login"
        element={accessToken ? <Navigate to="/dashboard" replace /> : <LoginPage />}
      />
      <Route
        path="/register"
        element={accessToken ? <Navigate to="/dashboard" replace /> : <RegisterPage />}
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/team"
        element={
          <ProtectedRoute>
            <TeamPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/invitations/accept"
        element={
          <ProtectedRoute>
            <AcceptInvitationPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/test-panel"
        element={
          <ProtectedRoute>
            <TestPanelPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/knowledge"
        element={
          <ProtectedRoute>
            <KnowledgePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/articles"
        element={
          <ProtectedRoute>
            <ArticlesPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/articles/:id"
        element={
          <ProtectedRoute>
            <ArticleEditorPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/publish-targets"
        element={
          <ProtectedRoute>
            <PublishTargetsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/wechat-config"
        element={
          <ProtectedRoute>
            <WechatConfigPage />
          </ProtectedRoute>
        }
      />
      <Route path="/" element={<Navigate to={accessToken ? '/dashboard' : '/login'} replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
