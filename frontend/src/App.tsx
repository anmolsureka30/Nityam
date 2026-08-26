import { Navigate, Route, Routes } from "react-router-dom";
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
      <Route path="/" element={<HomeScreen />} />
      <Route path="/intensity/:conceptId" element={<IntensityScreen />} />
      <Route path="/session" element={<SessionScreen />} />
      <Route path="/readiness" element={<ReadinessScreen />} />
      <Route path="/summary" element={<SummaryScreen />} />
      <Route path="/teacher" element={<TeacherClassScreen />} />
      <Route path="/teacher/intervene" element={<TeacherIntervene />} />
      <Route path="/teacher/insights" element={<TeacherInsights />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
