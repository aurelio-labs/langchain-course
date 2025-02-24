export type Step = {
  name: string;
  result: Record<string, string | undefined>;
};

export type ChatOutput = {
  question: string;
  steps: Step[];
  result: {
    answer: string;
    tools_used: string[];
  };
};
