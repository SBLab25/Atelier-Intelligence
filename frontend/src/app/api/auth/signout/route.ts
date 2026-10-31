import { NextResponse } from "next/server";
import { endSession } from "@/lib/session";

export async function POST(): Promise<NextResponse> {
  await endSession();
  return NextResponse.json({ ok: true, redirect: "/signed-out" });
}
