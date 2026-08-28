import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import LoginScreen from "./features/auth/LoginScreen";
import HomeScreen from "./features/home/HomeScreen";
import IntensityScreen from "./features/intensity/IntensityScreen";
import SessionScreen from "./features/session/SessionScreen";
import ReadinessScreen from "./features/readiness/ReadinessScreen";
import SummaryScreen from "./features/summary/SummaryScreen";
import TeacherClassScreen from "./features/teacher/TeacherClassScreen";
import TeacherIntervene from "./features/teacher/TeacherIntervene";
import TeacherInsights from "./features/teacher/TeacherInsights";

/* Screens are URL-addressable so a demo can be resumed anywhere, and so the
   session can be deep-linked from a notification later. */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route path="/" element={<ProtectedRoute><HomeScreen /></ProtectedRoute>} />
      <Route path="/intensity/:conceptId" element={<ProtectedRoute><IntensityScreen /></ProtectedRoute>} />
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
