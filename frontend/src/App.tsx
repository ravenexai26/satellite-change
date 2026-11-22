import { NavLink, Route, Routes } from "react-router-dom";
import Runs from "./pages/Runs";
import NewRun from "./pages/NewRun";
import RunView from "./pages/RunView";
import Method from "./pages/Method";
import Explore from "./pages/Explore";

const nav = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? "bg-white/15 text-white" : "text-navy-100 hover:bg-white/10 hover:text-white"}`;

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="bg-navy-800 text-white">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
          <NavLink to="/" className="flex items-center gap-3">
            <img src="/favicon.svg" alt="" className="h-8 w-8" />
            <div className="leading-tight">
              <div className="font-semibold">Ravenex Satellite Change</div>
              <div className="text-xs text-navy-100">River and char change detection · NESFIC-D-19</div>
            </div>
          </NavLink>
          <nav className="ml-auto flex gap-1">
            <NavLink to="/" end className={nav}>Analyses</NavLink>
            <NavLink to="/explore" className={nav}>Explore imagery</NavLink>
            <NavLink to="/new" className={nav}>New analysis</NavLink>
            <NavLink to="/method" className={nav}>Method & limits</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        <Routes>
          <Route path="/" element={<Runs />} />
          <Route path="/new" element={<NewRun />} />
          <Route path="/runs/:id/*" element={<RunView />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/method" element={<Method />} />
        </Routes>
      </main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap justify-between gap-2 px-6 py-4 text-xs text-slate-500">
          <span>Every alert is a lead for verification by authorised personnel. The system describes physical change in land and water only.</span>
          <span>Runs on this computer · Contains modified Copernicus Sentinel data · © 2026 Ravenex Technologies</span>
        </div>
      </footer>
    </div>
  );
}
