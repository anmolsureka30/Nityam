import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import LoginScreen from "./features/auth/LoginScreen";
import HomeScreen from "./features/home/HomeScreen";
import IntensityScreen from "./features/intensity/IntensityScreen";
import ProfileScreen from "./features/profile/ProfileScreen";
import SessionScreen from "./features/session/SessionScreen";
import ReadinessScreen from "./features/readiness/ReadinessScreen";
import SummaryScreen from "./features/summary/SummaryScreen";
import TeacherClassScreen from "./features/teacher/TeacherClassScreen";
import TeacherIntervene from "./features/teacher/TeacherIntervene";
import TeacherInsights from "./features/teacher/TeacherInsights";
import { useAuth } from "./lib/auth/AuthContext";
import { LANDING_URL } from "./lib/landingUrl";

/* The root path is the one place this app is reached "cold" — someone
   typing the URL, or a bookmark — rather than via a link this app itself
   generated (every internal link already knows where it's going). A signed-
   in visitor is home; a signed-out one has not seen the landing page yet,
   which lives entirely outside this app (../Nityam), so this is a real
   browser navigation, not a React Router route. Every OTHER protected route
   still bounces straight to /login on sign-out — that is correct there: a
   session expiring mid-page should not eject the student to the marketing
   site, it should ask them to sign back in and return them to where they
   were (ProtectedRoute's `state={{ from: location }}` already does that). */
function RootGate() {
  const { user, loading } = useAuth();
  useEffect(() => {
    if (!loading && !user) window.location.replace(LANDING_URL);
  }, [loading, user]);

  if (loading || !user) return null;
  return <HomeScreen />;
}

/* Screens are URL-addressable so a demo can be resumed anywhere, and so the
   session can be deep-linked from a notification later. */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route path="/" element={<RootGate />} />
      <Route path="/intensity/:conceptId" element={<ProtectedRoute><IntensityScreen /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><ProfileScreen /></ProtectedRoute>} />
      <Route path="/session" element={<ProtectedRoute><SessionScreen /></ProtectedRoute>} />
      <Route path="/readiness" element={<ProtectedRoute><ReadinessScreen /></ProtectedRoute>} />
      <Route path="/summary" element={<ProtectedRoute><SummaryScreen /></ProtectedRoute>} />
      <Route path="/teacher" element={<ProtectedRoute><TeacherClassScreen /></ProtectedRoute>} />
      <Route path="/teacher/intervene" element={<ProtectedRoute><TeacherIntervene /></ProtectedRoute>} />
      <Route path="/teacher/insights" element={<ProtectedRoute><TeacherInsights /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
