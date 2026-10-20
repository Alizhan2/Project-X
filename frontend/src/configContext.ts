import { createContext, useContext } from 'react'

export interface AppConfig { launch_mode: string; simulated: boolean; registration_enabled: boolean; release: string }
// Until the server answers we assume the most cautious wording (simulated), never an unlabeled "real" mode.
export const DEFAULT_CONFIG: AppConfig = { launch_mode: 'development', simulated: true, registration_enabled: true, release: 'unknown' }
export const ConfigContext = createContext<AppConfig>(DEFAULT_CONFIG)
export const useConfig = () => useContext(ConfigContext)
