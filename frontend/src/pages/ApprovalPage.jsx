import AcceptanceApprovalPage from "./acceptance/AcceptanceApprovalPage";
import InitiationApprovalPage from "./initiation/InitiationApprovalPage";
import TaskOrderApprovalPage from "./taskOrder/TaskOrderApprovalPage";
import { normalizeScene } from "../api";

export default function ApprovalPage({ scene = "initiation" }) {
  const activeScene = normalizeScene(scene);
  if (activeScene === "acceptance") {
    return <AcceptanceApprovalPage />;
  }
  if (activeScene === "task_order") {
    return <TaskOrderApprovalPage />;
  }
  return <InitiationApprovalPage />;
}
