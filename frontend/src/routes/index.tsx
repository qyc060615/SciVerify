import { createBrowserRouter, Navigate } from 'react-router-dom'
import RootLayout from '@/layouts/RootLayout'
import AppLayout from '@/layouts/AppLayout'
import LandingPage from '@/pages/LandingPage'
import { GuestRoute, ProtectedRoute } from '@/routes/ProtectedRoute'
import UiPreviewPage from '@/pages/UiPreviewPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import AppHomePage from '@/pages/AppHomePage'
import VerifyPage from '@/pages/VerifyPage'
import HistoryPage from '@/pages/HistoryPage'
import SettingsPage from '@/pages/SettingsPage'
import { ROUTES } from '@/constants'
import WholePaperVerifyPage from '@/pages/WholePaperVerifyPage'
import WholePaperJobPage from '@/pages/WholePaperJobPage'
import { WholePaperRoute } from '@/routes/WholePaperRoute'

export const router = createBrowserRouter([
  {
    path: ROUTES.HOME,
    element: <LandingPage />,
  },
  {
    element: <RootLayout />,
    children: [
      {
        path: ROUTES.UI_PREVIEW,
        element: <UiPreviewPage />,
      },
      {
        element: <GuestRoute />,
        children: [
          {
            path: 'login',
            element: <LoginPage />,
          },
          {
            path: 'register',
            element: <RegisterPage />,
          },
        ],
      },
      {
        path: 'forgot-password',
        element: <ForgotPasswordPage />,
      },
      {
        path: 'reset-password',
        element: <ResetPasswordPage />,
      },
    ],
  },
  {
    path: ROUTES.APP,
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            element: <WholePaperRoute />,
            children: [
              { path: 'manuscripts', element: <WholePaperVerifyPage /> },
              { path: 'manuscripts/jobs/:jobId', element: <WholePaperJobPage /> },
            ],
          },
          {
            index: true,
            element: <Navigate to={ROUTES.APP_HOME} replace />,
          },
          {
            path: 'home',
            element: <AppHomePage />,
          },
          {
            path: 'verify/:verificationId',
            element: <VerifyPage />,
          },
          {
            path: 'verify',
            element: <VerifyPage />,
          },
          {
            path: 'history',
            element: <HistoryPage />,
          },
          {
            path: 'settings',
            element: <SettingsPage />,
          },
        ],
      },
    ],
  },
])
