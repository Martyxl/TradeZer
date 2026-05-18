import { api } from "@/lib/api";
import { TrafficLight } from "@/components/TrafficLight";
import { formatDateTime } from "@/lib/utils";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";

interface Props {
  params: { id: string };
}

export default async function NewsDetailPage({ params }: Props) {
  let item;
  try {
    item = await api.getNewsDetail(Number(params.id));
  } catch {
    notFound();
  }

  const pred = item.prediction;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <Link
        href="/"
        className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-white transition-colors"
      >
        <ArrowLeft size={14} />
        Zpět na dashboard
      </Link>

      <article className="rounded-2xl border border-[#2a2d3a] bg-[#1a1d27] p-6 space-y-5">
        {/* Meta */}
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span>{item.source_name}</span>
          <span>·</span>
          <span>{formatDateTime(item.published_at)}</span>
        </div>

        {/* Title */}
        <h1 className="text-xl font-bold text-white leading-snug">{item.title}</h1>

        {/* Prediction */}
        {pred && (
          <div className="flex items-center gap-6 rounded-xl bg-[#0f1117] border border-[#2a2d3a] p-4">
            <TrafficLight
              probs={{ down: pred.prob_down, neutral: pred.prob_neutral, up: pred.prob_up }}
              size="lg"
              showLabels
            />
            <div className="flex-1">
              <p className="text-xs text-gray-500 mb-1.5 font-medium uppercase tracking-wider">
                Predikce dopadu
              </p>
              <p className="text-sm text-gray-200 leading-relaxed">{pred.llm_reasoning}</p>
              <p className="mt-2 text-xs text-gray-600">
                Model: {pred.model_version} · Confidence: {(pred.confidence * 100).toFixed(0)}%
              </p>
            </div>
          </div>
        )}

        {/* Body */}
        {item.body && (
          <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
            {item.body}
          </div>
        )}

        {/* Categories */}
        {item.categories.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {item.categories.map((cat) => (
              <span
                key={cat}
                className="rounded-full bg-gray-800 px-3 py-1 text-xs text-gray-400"
              >
                {cat}
              </span>
            ))}
          </div>
        )}

        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-sm text-blue-500 hover:text-blue-400 transition-colors"
        >
          Otevřít původní zprávu <ExternalLink size={12} />
        </a>
      </article>
    </div>
  );
}
