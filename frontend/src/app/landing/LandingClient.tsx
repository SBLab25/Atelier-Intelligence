"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { LandingPage } from "@/cockpit/components/screens/LandingPage";
import { initialTasks } from "@/cockpit/data/mockData";
import type { Task } from "@/cockpit/types";

export function LandingClient() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>(initialTasks);

  const handleToggleTask = (taskId: string) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId
          ? { ...t, completed: !t.completed, status: !t.completed ? "done" : "in_progress" }
          : t
      )
    );
  };

  return (
    <LandingPage
      tasks={tasks}
      onToggleTask={handleToggleTask}
      onLaunchCockpit={() => router.push("/dashboard")}
      onSignIn={() => router.push("/login")}
      onViewAnalytics={() => router.push("/analytics")}
    />
  );
}

