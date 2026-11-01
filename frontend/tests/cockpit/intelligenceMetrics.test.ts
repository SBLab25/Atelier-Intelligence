import { describe, expect, it } from 'vitest';
import {
  calculateSprintSimulation,
  prioritizeSignals,
  type SimulationParams,
  type IntelligenceSignal,
} from '@/cockpit/utils/intelligenceMetrics';

describe('intelligence metrics utilities', () => {
  it('calculateSprintSimulation computes accurate days and risk level', () => {
    const onTrackParams: SimulationParams = {
      teamCapacityHours: 160,
      storyPointsEstimate: 80,
      velocityPerEngineerDay: 2.0,
      engineersCount: 4, // 8 pts/day -> 80 pts = 10 days
      scopeCreepPercent: 0,
    };

    const res1 = calculateSprintSimulation(onTrackParams);
    expect(res1.projectedDays).toBe(10);
    expect(res1.riskLevel).toBe('low');
    expect(res1.completionProbability).toBeGreaterThanOrEqual(90);

    // Over-capacity scenario (scope creep +25%)
    const delayedParams: SimulationParams = {
      teamCapacityHours: 160,
      storyPointsEstimate: 80,
      velocityPerEngineerDay: 2.0,
      engineersCount: 4,
      scopeCreepPercent: 25, // 100 pts -> 12.5 days (>1.15 ratio)
    };

    const res2 = calculateSprintSimulation(delayedParams);
    expect(res2.projectedDays).toBe(12.5);
    expect(res2.riskLevel).toBe('elevated');
    expect(res2.completionProbability).toBeLessThan(70);
  });

  it('prioritizeSignals sorts descending by impact score', () => {
    const signals: IntelligenceSignal[] = [
      {
        id: '1',
        category: 'velocity',
        severity: 'optimal',
        title: 'High throughput',
        metricLabel: 'Pts',
        metricValue: '98',
        confidence: 94,
        recommendation: 'Keep pace',
        impactScore: 65,
      },
      {
        id: '2',
        category: 'risk',
        severity: 'critical',
        title: 'API bottleneck',
        metricLabel: 'Delay',
        metricValue: '+2.4d',
        confidence: 96,
        recommendation: 'Reallocate 1 FTE',
        impactScore: 92,
      },
      {
        id: '3',
        category: 'capacity',
        severity: 'warning',
        title: 'Review queue',
        metricLabel: 'Backlog',
        metricValue: '6 PRs',
        confidence: 88,
        recommendation: 'Batch reviews',
        impactScore: 78,
      },
    ];

    const sorted = prioritizeSignals(signals);
    expect(sorted[0]?.id).toBe('2');
    expect(sorted[1]?.id).toBe('3');
    expect(sorted[2]?.id).toBe('1');
  });
});
