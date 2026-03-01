"use client";

import { useState } from "react";
import { 
  Sparkles, 
  ChevronUp, 
  ChevronDown, 
  BookOpen, 
  GitBranch, 
  Zap, 
  Crown, 
  CheckCircle2, 
  Check, 
  AlertTriangle, 
  Info,
  Star,
} from "lucide-react";

interface EditSummaryCardProps {
  editorNotes: string;
  clipCount: number;
  totalDuration: number;
  targetDuration: number;
  recipeDetails?: string;
  dishName?: string;
}

export function EditSummaryCard({
  editorNotes,
  clipCount,
  totalDuration,
  targetDuration,
  recipeDetails,
  dishName,
}: EditSummaryCardProps) {
  const [dismissed, setDismissed] = useState(false);

  // Parse editor notes to extract key insights
  const parseNotes = () => {
    if (!editorNotes) return null;

    const insights: {
      recipe?: string;
      flow?: string;
      keyMoments?: string[];
      duration?: string;
    } = {};

    // Extract recipe/dish
    const recipeMatch = editorNotes.match(/This is (?:a |an )?([^.]+)\./i);
    if (recipeMatch) {
      insights.recipe = recipeMatch[1];
    }

    // Extract flow/story structure
    const flowMatch = editorNotes.match(/Edit flow[s]?:\s*([^.]+(?:→[^.]+)*)/i);
    if (flowMatch) {
      insights.flow = flowMatch[1];
    }

    // Extract key moments
    const momentMatch = editorNotes.match(/Key moment[s]?:\s*([^.]+(?:,[^.]+)*)/i);
    if (momentMatch) {
      // Split by commas and clean up
      insights.keyMoments = momentMatch[1]
        .split(",")
        .map((m) => m.trim())
        .filter((m) => m.length > 0);
    }

    // Extract duration info
    const durationMatch = editorNotes.match(/(\d+\.?\d*)\s*(?:second|sec|s)\b/i);
    if (durationMatch) {
      insights.duration = durationMatch[0];
    }

    return insights;
  };

  const insights = parseNotes();

  // Find the best/hero moment from editor notes
  const findHeroMoment = (): string | null => {
    if (!editorNotes) return null;

    const heroPatterns = [
      /chocolate (?:pull|ooze|pour|drizzle)/i,
      /cheese pull/i,
      /(?:final|hero|money) (?:shot|moment|reveal)/i,
      /plat(?:ing|ed)/i,
      /golden (?:flip|brown|crisp)/i,
      /sizzl(?:e|ing)/i,
    ];

    for (const pattern of heroPatterns) {
      const match = editorNotes.match(pattern);
      if (match) {
        // Try to find surrounding context
        const index = editorNotes.indexOf(match[0]);
        const contextStart = Math.max(0, index - 40);
        const contextEnd = Math.min(editorNotes.length, index + match[0].length + 40);
        return editorNotes.substring(contextStart, contextEnd).trim();
      }
    }

    return null;
  };

  const heroMoment = findHeroMoment();

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  if (dismissed) {
    // Compact header version
    return (
      <div className="max-w-2xl mx-auto mb-6">
        <div
          onClick={() => setDismissed(false)}
          className="bg-accent/5 border border-accent/20 rounded-lg p-3 flex items-center justify-between cursor-pointer hover:bg-accent/10 transition-all duration-200"
        >
          <div className="flex items-center gap-3">
            <Sparkles className="w-6 h-6 text-accent fill-accent" strokeWidth={0} />
            <div>
              <p className="text-sm font-semibold text-white">
                {insights?.recipe || dishName || "Your Edit is Ready"}
              </p>
              <p className="text-xs text-gray-400">
                {clipCount} clips · {formatTime(totalDuration)} · Click to expand
              </p>
            </div>
          </div>
          <ChevronDown className="w-5 h-5 text-gray-400 hover:text-white transition-colors" strokeWidth={2} />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto mb-6">
      <div className="bg-gradient-to-br from-accent/10 via-accent/5 to-transparent border border-accent/20 rounded-2xl p-6 relative overflow-hidden">
        {/* Decorative gradient */}
        <div className="absolute -top-10 -right-10 w-40 h-40 bg-accent/10 rounded-full blur-3xl" />
        
        {/* Dismiss button */}
        <button
          onClick={() => setDismissed(true)}
          className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors"
          title="Minimize"
        >
          <ChevronUp className="w-5 h-5" strokeWidth={2} />
        </button>

        {/* Header */}
        <div className="flex items-start gap-3 mb-5 relative z-10">
          <Sparkles className="w-7 h-7 text-accent fill-accent" strokeWidth={0} />
          <div>
            <h2 className="text-xl font-bold text-white mb-1">Your Edit is Ready!</h2>
            <p className="text-sm text-gray-400">
              AI analyzed your footage and created an intelligent edit
            </p>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-4 mb-5 relative z-10">
          <div className="bg-white/5 rounded-lg p-3 text-center border border-white/10">
            <p className="text-2xl font-bold text-accent">{clipCount}</p>
            <p className="text-xs text-gray-400 mt-1">Clips Selected</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3 text-center border border-white/10">
            <p className="text-2xl font-bold text-accent">{formatTime(totalDuration)}</p>
            <p className="text-xs text-gray-400 mt-1">Total Duration</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3 text-center border border-green-400/20 bg-green-400/5">
            <div className="flex items-center justify-center mb-1">
              <CheckCircle2 className="w-6 h-6 text-green-400" strokeWidth={2} />
            </div>
            <p className="text-xs text-gray-400">Story Complete</p>
          </div>
        </div>

        {/* Insights */}
        <div className="space-y-3 relative z-10">
          {/* Recipe/Dish */}
          {insights?.recipe && (
            <div className="flex items-start gap-2">
              <span className="text-accent font-semibold text-sm flex items-center gap-2 shrink-0"><BookOpen className="w-4 h-4" strokeWidth={2} /> Recipe:</span>
              <span className="text-sm text-gray-300">{insights.recipe}</span>
            </div>
          )}

          {/* Story Flow */}
          {insights?.flow && (
            <div className="flex items-start gap-2">
              <span className="text-accent font-semibold text-sm flex items-center gap-2 shrink-0"><GitBranch className="w-4 h-4" strokeWidth={2} /> Flow:</span>
              <span className="text-sm text-gray-300">{insights.flow}</span>
            </div>
          )}

          {/* Key Moments */}
          {insights?.keyMoments && insights.keyMoments.length > 0 && (
            <div>
              <span className="text-accent font-semibold text-sm flex items-center gap-2 mb-2"><Zap className="w-4 h-4 fill-accent text-accent" strokeWidth={0} /> Key Moments:</span>
              <ul className="space-y-1 ml-6">
                {insights.keyMoments.slice(0, 3).map((moment, idx) => (
                  <li key={idx} className="text-sm text-gray-300 flex items-start gap-2">
                    <span className="text-accent">•</span>
                    <span>{moment}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Hero Moment Highlight */}
          {heroMoment && (
            <div className="mt-4 bg-accent/10 border border-accent/30 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <Star className="w-5 h-5 text-accent fill-accent" strokeWidth={0} />
                <div>
                  <p className="text-sm font-semibold text-accent mb-1">Best Moment</p>
                  <p className="text-xs text-gray-300">{heroMoment}</p>
                </div>
              </div>
            </div>
          )}

          {/* Duration match */}
          {targetDuration && (
            <div className="flex items-center gap-2 text-xs mt-4">
              {totalDuration >= targetDuration - 5 && totalDuration <= targetDuration + 5 ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-green-400" strokeWidth={2} />
                  <span className="text-gray-400">
                    Perfect duration ({formatTime(totalDuration)} / {formatTime(targetDuration)} target)
                  </span>
                </>
              ) : totalDuration > targetDuration + 5 ? (
                <>
                  <AlertTriangle className="w-4 h-4 text-yellow-400" strokeWidth={2} />
                  <span className="text-gray-400">
                    Slightly over target ({formatTime(totalDuration)} / {formatTime(targetDuration)})
                  </span>
                </>
              ) : (
                <>
                  <Info className="w-4 h-4 text-blue-400" strokeWidth={2} />
                  <span className="text-gray-400">
                    Under target ({formatTime(totalDuration)} / {formatTime(targetDuration)})
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
