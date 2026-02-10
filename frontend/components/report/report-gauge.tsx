"use client";

import { PieChart, Pie, Cell } from "recharts";
import { ChartContainer } from "@/components/ui/chart";

interface GaugeProps {
  value: number;
  min: number;
  max: number;
  label: string;
  sublabel?: string;
  zones: Array<{ from: number; to: number; color: string }>;
}

export function ReportGauge({ value, min, max, label, sublabel, zones }: GaugeProps) {
  const range = max - min;
  const clampedValue = Math.max(min, Math.min(max, value));
  const angle = ((clampedValue - min) / range) * 180;

  // Build pie segments from zones
  const data = zones.map((zone) => ({
    value: ((zone.to - zone.from) / range) * 100,
    color: zone.color,
  }));

  // Needle SVG
  const needleAngle = 180 - angle; // PieChart goes from 180 to 0
  const radians = (needleAngle * Math.PI) / 180;
  const cx = 150;
  const cy = 120;
  const needleLength = 75;
  const nx = cx + needleLength * Math.cos(radians);
  const ny = cy - needleLength * Math.sin(radians);

  const chartConfig = {
    value: { label: "Value" },
  };

  return (
    <div className="flex flex-col items-center">
      <ChartContainer config={chartConfig} className="h-[160px] w-[300px]">
        <PieChart width={300} height={160}>
          <Pie
            data={data}
            cx={150}
            cy={120}
            startAngle={180}
            endAngle={0}
            innerRadius={55}
            outerRadius={90}
            dataKey="value"
            stroke="none"
          >
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.color} />
            ))}
          </Pie>
          {/* Needle */}
          <svg>
            <line
              x1={cx}
              y1={cy}
              x2={nx}
              y2={ny}
              stroke="hsl(var(--foreground))"
              strokeWidth={2.5}
            />
            <circle cx={cx} cy={cy} r={5} fill="hsl(var(--foreground))" />
          </svg>
        </PieChart>
      </ChartContainer>
      <div className="text-center -mt-4">
        <div className="text-2xl font-bold text-foreground">{label}</div>
        {sublabel && (
          <div className="text-sm text-muted-foreground">{sublabel}</div>
        )}
      </div>
    </div>
  );
}
