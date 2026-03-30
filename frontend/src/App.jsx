import { Navigate, Route, Routes } from "react-router-dom";
import AcceptanceApprovalPage from "./pages/acceptance/AcceptanceApprovalPage";
import AcceptanceReviewFeedbackPage from "./pages/acceptance/AcceptanceReviewFeedbackPage";
import InitiationApprovalPage from "./pages/initiation/InitiationApprovalPage";
import InitiationReviewFeedbackPage from "./pages/initiation/InitiationReviewFeedbackPage";
import ProjectViewerPage from "./pages/ProjectViewerPage";
import SceneHomePage from "./pages/SceneHomePage";
import SkillsPage from "./pages/SkillsPage";
import TaskOrderApprovalPage from "./pages/taskOrder/TaskOrderApprovalPage";
import TaskOrderReviewFeedbackPage from "./pages/taskOrder/TaskOrderReviewFeedbackPage";
import WorkbenchPage from "./pages/WorkbenchPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/initiation" replace />} />
      <Route path="/initiation" element={<SceneHomePage scene="initiation" />} />
      <Route path="/initiation/projects" element={<InitiationApprovalPage />} />
      <Route path="/initiation/home" element={<Navigate to="/initiation" replace />} />
      <Route path="/initiation/review-feedback" element={<InitiationReviewFeedbackPage />} />
      <Route path="/initiation/skills" element={<SkillsPage scene="initiation" />} />
      <Route path="/acceptance" element={<SceneHomePage scene="acceptance" />} />
      <Route path="/acceptance/projects" element={<AcceptanceApprovalPage />} />
      <Route path="/acceptance/review-feedback" element={<AcceptanceReviewFeedbackPage />} />
      <Route path="/acceptance/skills" element={<SkillsPage scene="acceptance" />} />
      <Route path="/task-order" element={<SceneHomePage scene="task_order" />} />
      <Route path="/task-order/projects" element={<TaskOrderApprovalPage />} />
      <Route path="/task-order/review-feedback" element={<TaskOrderReviewFeedbackPage />} />
      <Route path="/task-order/skills" element={<SkillsPage scene="task_order" />} />
      <Route path="/project/:projectId" element={<ProjectViewerPage />} />
      <Route path="/workbench" element={<WorkbenchPage />} />
      <Route path="/approval" element={<Navigate to="/initiation/projects" replace />} />
      <Route path="/review-feedback" element={<Navigate to="/initiation/review-feedback" replace />} />
      <Route path="/skills" element={<Navigate to="/initiation/skills" replace />} />
      <Route path="*" element={<Navigate to="/initiation" replace />} />
    </Routes>
  );
}
