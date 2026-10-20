import { useSyncExternalStore } from 'react'
import { getLanguage, subscribeLanguage } from './i18n'
export function useLanguage() {
  return useSyncExternalStore(subscribeLanguage, getLanguage, () => 'en' as const)
}
