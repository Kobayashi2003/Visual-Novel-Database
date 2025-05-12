import { Jim_Nightshade } from "next/font/google"

interface Row2Props {
  label: string
  value: React.ReactNode
}

export function Row2({ label, value }: Row2Props) {
  if (!value) return null

  return (
    <div className="flex flex-col gap-1">
      <h3 className="font-bold md:text-center text-white/60">{label}</h3>
      <div className="flex items-center text-xs md:text-sm">
        {value}
      </div>
    </div>
  )
}
