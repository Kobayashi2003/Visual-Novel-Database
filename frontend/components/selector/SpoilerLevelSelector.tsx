import { cn } from "@/lib/utils";
import { LevelSelectorButton, LevelSelectorSelect } from "@/components/selector/LevelSelector";

const spoilerLevelButtonOptions = [
  {
    key: "spoiler-level-button-safe",
    value: "0",
    label: "Hide spoilers",
    selectedClassName: "text-[#88ccff]",
    unselectedClassName: "text-white/80 hover:text-[#88ccff]/70",
    className: "font-bold",
  },
  {
    key: "spoiler-level-button-suggestive",
    value: "1",
    label: "Show minor spoilers",
    selectedClassName: "text-[#ffcc66]",
    unselectedClassName: "text-white/80 hover:text-[#ffcc66]/70",
    className: "font-bold",
  },
  {
    key: "spoiler-level-button-explicit",
    value: "2",
    label: "Spoil me!",
    selectedClassName: "text-[#ff6666]",
    unselectedClassName: "text-white/80 hover:text-[#ff6666]/70",
    className: "font-bold",
  }
]

const spoilerLevelSelectOptions = [
  {
    key: "spoiler-level-select-safe",
    value: "0",
    label: "🟢Hide",
  },
  {
    key: "spoiler-level-select-suggestive",
    value: "1",
    label: "🟡Minor",
  },
  {
    key: "spoiler-level-select-explicit",
    value: "2",
    label: "🔴Spoil",
  }
]

interface SpoilerLevelSelectorProps {
  spoilerLevel: string
  setSpoilerLevel: (value: string) => void
  disabled?: boolean
  className?: string
}

export function SpoilerLevelSelector({ spoilerLevel, setSpoilerLevel, disabled, className }: SpoilerLevelSelectorProps) {
  return (
    <>
      <LevelSelectorButton
        levelOptions={spoilerLevelButtonOptions}
        selectedLevel={spoilerLevel}
        setSelectedLevel={setSpoilerLevel}
        disabled={disabled}
        className={cn(
          "hidden lg:flex",
          "font-serif italic",
          "border-b border-white/50",
          className
        )}
      />
      <LevelSelectorSelect
        levelOptions={spoilerLevelSelectOptions}
        selectedLevel={spoilerLevel}
        setSelectedLevel={setSpoilerLevel}
        disabled={disabled}
        className={cn(
          "lg:hidden",
          className
        )}
      />
    </>
  )
}