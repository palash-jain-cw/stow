import { useEffect } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, queryKeys } from '../api/api'

interface FinancialYear { id: number }

export function RequireSetup() {
  const navigate = useNavigate()
  const { data: fys, isSuccess } = useQuery<FinancialYear[]>({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<FinancialYear[]>('/financial-years'),
    staleTime: 0,
  })

  useEffect(() => {
    if (isSuccess && fys.length === 0) {
      navigate('/onboarding', { replace: true })
    }
  }, [isSuccess, fys, navigate])

  return <Outlet />
}
