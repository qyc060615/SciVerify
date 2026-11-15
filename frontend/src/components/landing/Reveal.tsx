import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { useInView } from '@/hooks/useInView'

interface RevealProps {
  children: ReactNode
  className?: string
  delay?: number
}

export function Reveal({ children, className, delay = 0 }: RevealProps) {
  const { ref, inView } = useInView()

  return (
    <div
      ref={ref}
      className={cn(
        'reveal-motion transition-all duration-700 ease-out',
        inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0',
        className,
      )}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}
