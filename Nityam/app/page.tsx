import Header from "./components/Header";
import Hero from "./components/Hero";
import ProblemStats from "./components/ProblemStats";
import HowItWorks from "./components/HowItWorks";
import AudienceSplit from "./components/AudienceSplit";
import Beliefs from "./components/Beliefs";
import Mission from "./components/Mission";
import Waitlist from "./components/Waitlist";
import Footer from "./components/Footer";

export default function Home() {
  return (
    <>
      <Header />
      <Hero />
      <ProblemStats />
      <HowItWorks />
      <AudienceSplit />
      <Beliefs />
      <Mission />
      <Waitlist />
      <Footer />
    </>
  );
}
