export interface FinancialYearBounds {
  id: number
  status: string
  start_date: string
  end_date: string
}

/** Find unlocked FY covering isoDate (YYYY-MM-DD), or undefined. */
export function resolveFyForDate(
  fys: FinancialYearBounds[],
  isoDate: string,
): FinancialYearBounds | undefined {
  return fys.find(
    fy =>
      fy.status !== 'locked' &&
      isoDate >= fy.start_date &&
      isoDate <= fy.end_date,
  )
}

export function formatFyLabel(fy: FinancialYearBounds): string {
  const startYear = fy.start_date.slice(0, 4)
  const endYear = fy.end_date.slice(2, 4)
  return `${startYear}–${endYear}`
}
