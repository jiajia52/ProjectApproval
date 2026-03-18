import { Navigate, Route, Routes } from "react-router-dom";
import ApprovalPage from "./pages/ApprovalPage";
import ProjectViewerPage from "./pages/ProjectViewerPage";
import ReviewFeedbackPage from "./pages/ReviewFeedbackPage";
import SkillsPage from "./pages/SkillsPage";
import WorkbenchPage from "./pages/WorkbenchPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/approval" replace />} />
      <Route path="/approval" element={<ApprovalPage />} />
      <Route path="/review-feedback" element={<ReviewFeedbackPage />} />
      <Route path="/project/:projectId" element={<ProjectViewerPage />} />
      <Route path="/workbench" element={<WorkbenchPage />} />
      <Route path="/skills" element={<SkillsPage />} />
      <Route path="*" element={<Navigate to="/approval" replace />} />
    </Routes>
  );
}
