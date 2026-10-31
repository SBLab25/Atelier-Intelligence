/**
 * Quantitative intelligence and scenario forecasting calculations
 */

export interface SimulationParams {
  teamCapacityHours: number;
  storyPointsEstimate: number;
  velocityPerEngineerDay: number;
  engineersCount: number;
  scopeCreepPercent: number;
}

export interface SimulationResult {
  projectedDays: number;
  completionProbability: number;
  riskLevel: 'low' | 'moderate' | 'elevated' | 'critical';
  confidenceScore: number;
  adjustedPoints: number;
}

export interface IntelligenceSignal {
  id: string;
  category: 'anomaly' | 'velocity' | 'capacity' | 'risk';
  severity: 'optimal' | 'warning' | 'critical';
  title: string;
  metricLabel: string;
  metricValue: string;
  confidence: number;
  recommendation: string;
  impactScore: number;
}

/**
 * Run sprint completion simulation based on quantitative levers
 */
export function calculateSprintSimulation(params: SimulationParams): SimulationResult {
  const adjustedPoints = Math.round(
    params.storyPointsEstimate * (1 + params.scopeCreepPercent / 100)
  );
  
  const dailyTeamVelocity = Math.max(0.1, params.engineersCount * params.velocityPerEngineerDay);
  const projectedDays = Math.round((adjustedPoints / dailyTeamVelocity) * 10) / 10;
  
  // Benchmark capacity: assumed 10 working days sprint
  const targetDays = 10;
  const ratio = projectedDays / targetDays;
  
  let riskLevel: 'low' | 'moderate' | 'elevated' | 'critical' = 'low';
  let completionProbability = 95;

  if (ratio <= 1.0) {
    riskLevel = 'low';
    completionProbability = Math.min(99, Math.round(98 - (ratio - 0.8) * 20));
  } else if (ratio <= 1.15) {
    riskLevel = 'moderate';
    completionProbability = Math.round(85 - (ratio - 1.0) * 80);
  } else if (ratio <= 1.3) {
    riskLevel = 'elevated';
    completionProbability = Math.round(70 - (ratio - 1.15) * 100);
  } else {
    riskLevel = 'critical';
    completionProbability = Math.max(15, Math.round(45 - (ratio - 1.3) * 60));
  }

  // Confidence based on sample parameters stability
  const confidenceScore = Math.min(99, Math.max(70, Math.round(92 - params.scopeCreepPercent * 0.4)));

  return {
    projectedDays,
    completionProbability,
    riskLevel,
    confidenceScore,
    adjustedPoints,
  };
}

/**
 * Filter and sort intelligence signals by impact score
 */
export function prioritizeSignals(signals: IntelligenceSignal[]): IntelligenceSignal[] {
  return [...signals].sort((a, b) => b.impactScore - a.impactScore);
}
