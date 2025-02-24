"use client";

import Output from "@/components/Output";
import TextArea from "@/components/TextArea";
import { type ChatOutput } from "@/types";
import { useState } from "react";

export default function Home() {
  const [outputs, setOutputs] = useState<ChatOutput[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);

  return (
    <div
      className={`container pt-10 pb-32 min-h-screen ${
        outputs.length === 0 && "flex items-center justify-center"
      }`}
    >
      <div className="w-full">
        {outputs.length === 0 && (
          <h1 className="text-4xl text-center mb-5">
            What do you want to know?
          </h1>
        )}

        <TextArea
          setIsGenerating={setIsGenerating}
          isGenerating={isGenerating}
          outputs={outputs}
          setOutputs={setOutputs}
        />

        {outputs.map((output, i) => {
          return <Output key={i} output={output} />;
        })}
      </div>
    </div>
  );
}
