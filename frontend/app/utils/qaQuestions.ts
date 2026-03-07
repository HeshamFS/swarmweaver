export interface QAOption {
  label: string;
  description: string;
}

export interface QAQuestion {
  question: string;
  options: QAOption[];
  context?: string;
}

export interface QAResponse {
  questions: QAQuestion[];
  skip_reason?: string;
}

export async function fetchQAQuestions(
  mode: string,
  taskInput: string,
  projectDir: string
): Promise<QAResponse> {
  const res = await fetch("/api/qa/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, task_input: taskInput, project_dir: projectDir }),
  });
  if (!res.ok) throw new Error(`QA generation failed: ${res.status}`);
  return res.json();
}
