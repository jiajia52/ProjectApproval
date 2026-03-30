import AcceptanceReviewFeedbackPage from "./acceptance/AcceptanceReviewFeedbackPage";
import InitiationReviewFeedbackPage from "./initiation/InitiationReviewFeedbackPage";
import TaskOrderReviewFeedbackPage from "./taskOrder/TaskOrderReviewFeedbackPage";
import { normalizeScene } from "../api";

export default function ReviewFeedbackPage({ scene = "initiation" }) {
  const activeScene = normalizeScene(scene);
  if (activeScene === "acceptance") {
    return <AcceptanceReviewFeedbackPage />;
  }
  if (activeScene === "task_order") {
    return <TaskOrderReviewFeedbackPage />;
  }
  return <InitiationReviewFeedbackPage />;
}
