/**
 * Single source of truth for the spoken presentation.
 * deck.js embeds `text` as PowerPoint speaker notes; make-speech.js renders SPEECH.md
 * from the same array, so the two can never drift apart.
 *
 * `seconds` is the delivery budget for the slide at a measured 134 words per minute.
 */
module.exports = [
  {
    n: 1,
    title: "Title — Amazon Lightsail (PaaS-Lite)",
    seconds: 16,
    cue: "Stand still. Let the title slide settle for two seconds before speaking.",
    text:
      "Good morning. My name is Hridiyansh Shukla, registration number 2427030591. " +
      "Today I am presenting on Amazon Lightsail — Amazon Web Services' fixed-price virtual private server, " +
      "and the reason so many people describe it as Platform-as-a-Service, lite.",
  },
  {
    n: 2,
    title: "Agenda",
    seconds: 18,
    cue: "Move briskly. Do not read all eight items aloud — gesture across them.",
    text:
      "I have structured this in eight parts. We begin with the problem Lightsail was built to solve. " +
      "We then open the service up — its anatomy, " +
      "its pricing, and its competitors — and we close with its limitations and my verdict.",
  },
  {
    n: 3,
    title: "The problem",
    seconds: 47,
    cue: "Point to the three statistics on the right when you reach the last sentence.",
    text:
      "Amazon EC2 is extraordinarily capable, and that is precisely the problem. " +
      "Before a raw EC2 instance serves a single request, you must design a virtual private cloud, a subnet, " +
      "a route table, an internet gateway, a security group, a storage volume, a key pair and an elastic IP address. " +
      "Second, the bill arrives on four separate meters — compute, storage, outbound data and the address itself — " +
      "so a small site simply cannot forecast next month's invoice. " +
      "And third, there is a skills mismatch: most people who want a website need a running server, " +
      "not a cloud architecture qualification. " +
      "The numbers on the right make the point.",
  },
  {
    n: 4,
    title: "Where Lightsail sits",
    seconds: 46,
    cue: "Trace the Lightsail column downward with your hand as you describe the three colours.",
    text:
      "Reading left to right: on-premises, you manage every layer. With Infrastructure-as-a-Service — EC2 — " +
      "Amazon takes the four hardware layers and hands you the operating system upward. " +
      "With true Platform-as-a-Service — Heroku, or Elastic Beanstalk — Amazon takes the operating system and the runtime too, " +
      "and you never meet a server. " +
      "Lightsail sits in between, and the teal band is why. Amazon pre-builds your operating system and your runtime, " +
      "exactly like a PaaS — and then hands you the root password anyway. " +
      "You get PaaS convenience on day one and IaaS control on day two. That hybrid position is the entire product.",
  },
  {
    n: 5,
    title: "What Lightsail is",
    seconds: 36,
    cue: "Emphasise 'nothing is a proprietary dead end' — it sets up slide 18.",
    text:
      "Formally, then: Lightsail is AWS's virtual private server offering — pre-configured compute, storage, networking " +
      "and managed services, sold as fixed-price monthly bundles through a deliberately simplified console. " +
      "It was announced at re:Invent on the thirtieth of November 2016, and it is still expanding — " +
      "Hong Kong, São Paulo and Spain were added as recently as June this year. " +
      "The fourth card matters most: instances are EC2, disks are EBS, DNS is Route 53. Nothing here is a proprietary dead end.",
  },
  {
    n: 6,
    title: "Architecture",
    seconds: 39,
    cue: "Follow the two orange arrows down the diagram as you speak.",
    text:
      "So how is it built? Lightsail is not a new infrastructure platform. It is a curated control plane over services " +
      "Amazon already sells. " +
      "The control plane holds the bundles, the blueprints and the opinionated defaults. " +
      "Underneath, every resource you create is an ordinary AWS primitive with most of its " +
      "configuration surface hidden — an instance is EC2, a load balancer is Elastic Load Balancing with a free certificate, " +
      "a distribution is CloudFront. " +
      "That hiding is the product. You are trading knobs for a price you can predict.",
  },
  {
    n: 7,
    title: "Resource catalogue",
    seconds: 26,
    cue: "Do not read the table. Name three rows and move on.",
    text:
      "Ten resource types cover the entire service. I will not read the table, but notice the shape of it: " +
      "instances and containers for compute; managed databases, block storage and buckets for state; " +
      "load balancers, distributions, DNS zones and static addresses for delivery. " +
      "The right-hand column is the honest one — every single row is an existing AWS service, simplified.",
  },
  {
    n: 8,
    title: "Blueprints and bundles",
    seconds: 40,
    cue: "The orange box is the most current fact in the deck. Slow down for it.",
    text:
      "Creating a server is therefore only two decisions. The blueprint is the software — a plain operating system, " +
      "or a ready-built stack such as WordPress, LAMP, Node.js or Magento, already installed. " +
      "The bundle is the hardware and the price, fixed together. " +
      "One point of currency, in the orange box: Amazon is retiring the Bitnami-packaged blueprints. " +
      "WordPress, LAMP, Nginx and Node.js images from Bitnami retire this November; the remainder follow in May 2027. " +
      "AWS-maintained replacements began shipping in January. If you are starting a project today, choose the AWS-maintained image.",
  },
  {
    n: 9,
    title: "Instance pricing",
    seconds: 40,
    cue: "Read only the first and last rows aloud. Then the three notes underneath.",
    text:
      "Here is the published price list for Linux general-purpose bundles. " +
      "Five dollars a month buys half a gigabyte of memory, two virtual CPUs, twenty gigabytes of solid-state storage " +
      "and a terabyte of outbound transfer. At the top, three hundred and eighty-four dollars buys sixty-four gigabytes " +
      "and eight terabytes of transfer. " +
      "Three things worth noting underneath. A public IPv4 address is now the premium — go IPv6-only and the entry tier " +
      "falls to three dollars fifty. Transfer beyond the allowance is metered. And selected entry bundles carry three months free.",
  },
  {
    n: 10,
    title: "The rest of the price list",
    seconds: 23,
    cue: "Point at the navy bar and deliver that line as the takeaway.",
    text:
      "Everything else follows the same pattern. Containers from seven dollars a node. A managed database from fifteen. " +
      "A load balancer at eighteen, certificate included. Object storage from one dollar, free for a year. " +
      "The line at the bottom is the one to remember: Amazon is selling you an allowance, not a meter.",
  },
  {
    n: 11,
    title: "Cost comparison",
    seconds: 47,
    cue: "Give the audience three seconds to read the chart before you explain it.",
    text:
      "This is where that matters. I priced a Lightsail Small bundle — twelve dollars, three terabytes of transfer " +
      "included — against the same thing built on EC2 at list price. " +
      "At a hundred gigabytes of traffic, EC2 costs about twenty-four dollars. " +
      "At three terabytes — the allowance you already paid for — two hundred and ninety-one dollars. " +
      "But let me be honest about that chart. Compute is not what drives the gap; data transfer is. " +
      "At low traffic the two are close, and EC2 wins ground back through Savings Plans. " +
      "Lightsail's real advantage is bandwidth included in the price, and a number you knew in advance.",
  },
  {
    n: 12,
    title: "Networking and security",
    seconds: 37,
    cue: "End on the red line at the bottom. Pause after it.",
    text:
      "Every instance carries its own default-deny firewall. " +
      "A load balancer issues and renews TLS certificates free of charge. A static IPv4 address costs nothing while attached. " +
      "And resources sit in a Lightsail-managed private cloud that peers with your main one in a single click. " +
      "But note the line at the bottom, because it is the most commonly misunderstood point about this service: " +
      "a simpler console does not shrink your security responsibility. Patching the operating system inside that blueprint is still your job.",
  },
  {
    n: 13,
    title: "Lightsail versus EC2",
    seconds: 37,
    cue: "Four rows only: pricing, scaling, discounts, best fit.",
    text:
      "Four rows tell the story. " +
      "Pricing: a fixed bundle against per-second metering. " +
      "Scaling: Lightsail has no auto scaling for instances at all — capacity is a manual decision. " +
      "Discounts: Lightsail has no Reserved Instances, no Savings Plans, no Spot. The list price is the price. " +
      "And best fit: predictable small workloads against elastic or compliance-heavy architectures. " +
      "But these two are not rivals. Lightsail is the on-ramp; EC2 is the motorway. " +
      "The snapshot export exists precisely so that the journey between them is cheap.",
  },
  {
    n: 14,
    title: "The wider market",
    seconds: 35,
    cue: "Concede the price point honestly — it strengthens the next sentence.",
    text:
      "Against the wider market, on raw price per gigabyte of memory, " +
      "Lightsail is competitive rather than cheapest. DigitalOcean starts lower; Linode gives more memory for the same five dollars. " +
      "Lightsail wins on two things a price list does not show. First, the included transfer allowance — which is exactly " +
      "where independent VPS bills tend to break. Second, the resource underneath is ordinary AWS, so outgrowing Lightsail " +
      "is a migration inside one account rather than a change of vendor.",
  },
  {
    n: 15,
    title: "Deployment walkthrough",
    seconds: 37,
    cue: "Count the six steps on your fingers. Land firmly on 'ten minutes'.",
    text:
      "In practice it looks like this. Pick the WordPress blueprint. Pick a bundle. Create the instance — it boots into a " +
      "running site in about a minute. Attach a static address. Point a DNS record at it. Enable HTTPS. " +
      "That is a live, secured, production WordPress site in under ten minutes. " +
      "The same result on raw EC2 needs all eight of those resources built and wired together first. " +
      "And none of this is console-only — every step is a single command-line call.",
  },
  {
    n: 16,
    title: "Use cases",
    seconds: 29,
    cue: "Two examples aloud, then the closing line.",
    text:
      "Websites and blogs, where the bandwidth allowance comfortably covers ordinary traffic. " +
      "Development and test environments that are created for a sprint and deleted afterwards. Small business applications " +
      "for teams with no operations staff. Storefronts, coursework, and research computing through Lightsail for Research. " +
      "The common thread is a workload whose ceiling is known in advance. " +
      "Lightsail is a poor fit the moment demand becomes genuinely unpredictable.",
  },
  {
    n: 17,
    title: "Limitations",
    seconds: 35,
    cue: "Deliver the navy bar as a considered judgement, not an apology.",
    text:
      "Which brings me to the limitations. " +
      "There is no auto scaling. There are no discount instruments. Access control is coarse, so Lightsail is unsuitable " +
      "wherever least-privilege access is formally audited. Entry bundles run on burstable CPU, which throttles under sustained load. " +
      "Now — none of these is a defect. Every one of them is the deliberate cost of a fixed price. " +
      "What matters is that each is also a signal that your workload may have outgrown the service.",
  },
  {
    n: 18,
    title: "Growth path",
    seconds: 35,
    cue: "This is the strategic argument. Deliver it as the strongest claim in the talk.",
    text:
      "Stay while traffic is predictable, the estate is small, and cost certainty matters more than tuning. " +
      "Move to EC2 when you need auto scaling, more than sixty-four gigabytes on one machine, proper identity management, " +
      "or Savings Plans economics. " +
      "And the exit is built in. Take a snapshot, export it to EC2, and Amazon creates a machine image and a volume snapshot " +
      "for you to launch. Your disk image is standard AWS — migration is a copy, not a rewrite.",
  },
  {
    n: 19,
    title: "Conclusion",
    seconds: 47,
    cue: "Slow down. One beat between each of the four points.",
    text:
      "To conclude, four things worth remembering. " +
      "First, Lightsail sells predictability, not power — the bundle is a price you know before you deploy. " +
      "Second, it is PaaS-Lite, not PaaS: Amazon pre-builds the operating system and runtime, then still gives you root. " +
      "Third, the saving is in the bandwidth, not the compute. " +
      "And fourth, its limitations are its exit signs — when they start to hurt, snapshot and export to EC2. " +
      "Lightsail is best understood not as a cheaper AWS, but as a narrower one, deliberately designed so that " +
      "outgrowing it is the expected outcome rather than a failure. Thank you. I am happy to take questions.",
  },
  {
    n: 20,
    title: "References",
    seconds: 12,
    cue: "Hold this slide during questions.",
    text:
      "My sources are listed here — principally the AWS Lightsail pricing pages, the user guide, and the service " +
      "announcements from 2026. I will leave this slide up.",
  },
];
