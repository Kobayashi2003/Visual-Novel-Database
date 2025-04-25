import { VN } from "@/lib/types"

interface VNTagsPanelProps {
  vn: VN
  spoilerLevel: "0" | "1" | "2"
}

export function VNTagsPanel({ vn, spoilerLevel }: VNTagsPanelProps) {

  return (
    <div>
      <h2>Tags</h2>
    </div>
  )
}