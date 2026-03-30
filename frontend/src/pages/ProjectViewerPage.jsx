import { useSearchParams } from "react-router-dom";
import AcceptanceProjectViewerPage from "./acceptance/AcceptanceProjectViewerPage";
import InitiationProjectViewerPage from "./initiation/InitiationProjectViewerPage";
import TaskOrderProjectViewerPage from "./taskOrder/TaskOrderProjectViewerPage";
import { normalizeScene } from "../api";

export default function ProjectViewerPage() {
  const [searchParams] = useSearchParams();
  const scene = normalizeScene(searchParams.get("scene"));
  if (scene === "acceptance") {
    return <AcceptanceProjectViewerPage />;
  }
  if (scene === "task_order") {
    return <TaskOrderProjectViewerPage />;
  }
  return <InitiationProjectViewerPage />;
}
