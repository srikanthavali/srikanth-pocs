import { NextResponse } from "next/server";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const jenkinsUrl = searchParams.get("jenkinsUrl");
  const jobName = searchParams.get("jobName");
  const buildNumber = searchParams.get("buildNumber");
  const start = searchParams.get("start") || 0;
  const username = searchParams.get("username");
  const apiToken = searchParams.get("apiToken");

  if (!jenkinsUrl || !jobName || !buildNumber || !username || !apiToken) {
    return NextResponse.json({ error: "Missing parameters" }, { status: 400 });
  }

  const upUrl = `${jenkinsUrl}/job/${encodeURIComponent(jobName)}/${buildNumber}/logText/progressiveText?start=${start}`;

  try {
    const upstream = await fetch(upUrl, {
      headers: {
        Authorization: "Basic " + Buffer.from(`${username}:${apiToken}`).toString("base64"),
      },
    });

    const text = await upstream.text();

    const headers = new Headers();
    const more = upstream.headers.get("x-more-data");
    const textSize = upstream.headers.get("x-text-size");
    if (more) headers.set("x-more-data", more);
    if (textSize) headers.set("x-text-size", textSize);

    return new Response(text, { status: upstream.status, headers });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
