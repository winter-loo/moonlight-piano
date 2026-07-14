import { notFound } from "next/navigation";

import { StageOnePractice } from "@/components/practice/StageOnePractice";

type PracticePageProps = {
  params: Promise<{ lessonId: string }>;
};

export default async function PracticePage({ params }: PracticePageProps) {
  const { lessonId } = await params;
  if (lessonId !== "B1-01" && lessonId !== "B1-02") notFound();
  return <StageOnePractice lessonId={lessonId} />;
}
