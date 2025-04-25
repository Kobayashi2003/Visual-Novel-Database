import { VN } from "@/lib/types"

interface VNScreenshotsPanelProps {
  vn: VN
  sexualLevel: "safe" | "suggestive" | "explicit"
  violenceLevel: "tame" | "violent" | "brutal"
}

export function VNScreenshotsPanel({ vn, sexualLevel, violenceLevel }: VNScreenshotsPanelProps) {

  return (
    <div>
      <h2>Screenshots</h2>
    </div>
  )
}