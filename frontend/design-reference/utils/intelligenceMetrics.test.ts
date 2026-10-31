import test from 'node:test';
import assert from 'node:assert/strict';
import {
  calculateSprintSimulation,
  prioritizeSignals,
  SimulationParams,
  IntelligenceSignal,
} from './intelligenceMetrics';

test('calculateSprintSimulation computes accurate days and risk level', () => {
  const onTrackParams: SimulationParams = {
    teamCapacityHours: 160,
    storyPointsEstimate: 80,
    velocityPerEngineerDay: 2.0,
    engineersCount: 4, // 8 pts/day -> 80 pts = 10 days
    scopeCreepPercent: 0,
  };

  const res1 = calculateSprintSimulation(onTrackParams);
  assert.equal(res1.projectedDays, 10);
  assert.equal(res1.riskLevel, 'low');
  assert.ok(res1.completionProbability >= 90);

  // Over-capacity scenario (scope creep +15%)
  const delayedParams: SimulationParams = {
    teamCapacityHours: 160,
    storyPointsEstimate: 80,
    velocityPerEngineerDay: 2.0,
    engineersCount: 4,
    scopeCreepPercent: 25, // 100 pts -> 12.5 days (>1.15 ratio)
  };

  const res2 = calculateSprintSimulation(delayedParams);
  assert.equal(res2.projectedDays, 12.5);
  assert.equal(res2.riskLevel, 'elevated');
  assert.ok(res2.completionProbability < 70);
});

test('prioritizeSignals sorts descending by impact score', () => {
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
  assert.equal(sorted[0].id, '2');
  assert.equal(sorted[1].id, '3');
  assert.equal(sorted[2].id, '1');
});
