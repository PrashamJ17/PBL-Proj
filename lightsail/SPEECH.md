# Presentation Speech — Amazon Lightsail (PaaS-Lite): Cloud Infrastructure

**Speaker:** Hridiyansh Shukla  
**Registration No.:** 2427030591  
**Deck:** `Amazon_Lightsail_Presentation.pptx` (20 slides)  
**Length:** 1528 words · **11:22** at a measured 134 words per minute

> This script is the single source of the speaker notes embedded in the `.pptx`.
> Every figure spoken aloud appears on the slide in front of you, so the two cannot contradict each other.

## How to hit the time

| If you speak at | The talk runs |
|---|---|
| 125 wpm (deliberate) | 12.2 min |
| 134 wpm (target) | 11.4 min |
| 145 wpm (brisk) | 10.5 min |

The whole range sits inside the 10–12 minute brief. Two checkpoints while presenting:
**slide 9 by 4:28** and **slide 15 by 8:07**. 
If you are running late at slide 15, compress slides 16 and 17 — they are the most cuttable.

If you must lose a minute, drop slide 14 (the market comparison) and slide 16 (use cases); 
the argument still holds without them. Never cut slides 4, 11 or 19 — they carry the thesis.

---

## Timing map

| Slide | Title | Enter at | Budget | Words |
|---:|---|---:|---:|---:|
| 1 | Title — Amazon Lightsail (PaaS-Lite) | 0:00 | 16s | 36 |
| 2 | Agenda | 0:16 | 18s | 41 |
| 3 | The problem | 0:34 | 47s | 107 |
| 4 | Where Lightsail sits | 1:21 | 46s | 102 |
| 5 | What Lightsail is | 2:07 | 36s | 80 |
| 6 | Architecture | 2:43 | 39s | 87 |
| 7 | Resource catalogue | 3:22 | 26s | 59 |
| 8 | Blueprints and bundles | 3:48 | 40s | 89 |
| 9 | Instance pricing | 4:28 | 40s | 89 |
| 10 | The rest of the price list | 5:08 | 23s | 52 |
| 11 | Cost comparison | 5:31 | 47s | 106 |
| 12 | Networking and security | 6:18 | 37s | 82 |
| 13 | Lightsail versus EC2 | 6:55 | 37s | 83 |
| 14 | The wider market | 7:32 | 35s | 78 |
| 15 | Deployment walkthrough | 8:07 | 37s | 82 |
| 16 | Use cases | 8:44 | 29s | 65 |
| 17 | Limitations | 9:13 | 35s | 78 |
| 18 | Growth path | 9:48 | 35s | 79 |
| 19 | Conclusion | 10:23 | 47s | 106 |
| 20 | References | 11:10 | 12s | 27 |
| | **Total** | | **11:22** | **1528** |

---

## The script

### Slide 1 — Title — Amazon Lightsail (PaaS-Lite)

`0:00 – 0:16`  ·  *16s · 36 words*

> **Delivery:** Stand still. Let the title slide settle for two seconds before speaking.

Good morning. My name is Hridiyansh Shukla, registration number 2427030591. Today I am presenting on Amazon Lightsail — Amazon Web Services' fixed-price virtual private server, and the reason so many people describe it as Platform-as-a-Service, lite.

### Slide 2 — Agenda

`0:16 – 0:34`  ·  *18s · 41 words*

> **Delivery:** Move briskly. Do not read all eight items aloud — gesture across them.

I have structured this in eight parts. We begin with the problem Lightsail was built to solve. We then open the service up — its anatomy, its pricing, and its competitors — and we close with its limitations and my verdict.

### Slide 3 — The problem

`0:34 – 1:21`  ·  *47s · 107 words*

> **Delivery:** Point to the three statistics on the right when you reach the last sentence.

Amazon EC2 is extraordinarily capable, and that is precisely the problem. Before a raw EC2 instance serves a single request, you must design a virtual private cloud, a subnet, a route table, an internet gateway, a security group, a storage volume, a key pair and an elastic IP address. Second, the bill arrives on four separate meters — compute, storage, outbound data and the address itself — so a small site simply cannot forecast next month's invoice. And third, there is a skills mismatch: most people who want a website need a running server, not a cloud architecture qualification. The numbers on the right make the point.

### Slide 4 — Where Lightsail sits

`1:21 – 2:07`  ·  *46s · 102 words*

> **Delivery:** Trace the Lightsail column downward with your hand as you describe the three colours.

Reading left to right: on-premises, you manage every layer. With Infrastructure-as-a-Service — EC2 — Amazon takes the four hardware layers and hands you the operating system upward. With true Platform-as-a-Service — Heroku, or Elastic Beanstalk — Amazon takes the operating system and the runtime too, and you never meet a server. Lightsail sits in between, and the teal band is why. Amazon pre-builds your operating system and your runtime, exactly like a PaaS — and then hands you the root password anyway. You get PaaS convenience on day one and IaaS control on day two. That hybrid position is the entire product.

### Slide 5 — What Lightsail is

`2:07 – 2:43`  ·  *36s · 80 words*

> **Delivery:** Emphasise 'nothing is a proprietary dead end' — it sets up slide 18.

Formally, then: Lightsail is AWS's virtual private server offering — pre-configured compute, storage, networking and managed services, sold as fixed-price monthly bundles through a deliberately simplified console. It was announced at re:Invent on the thirtieth of November 2016, and it is still expanding — Hong Kong, São Paulo and Spain were added as recently as June this year. The fourth card matters most: instances are EC2, disks are EBS, DNS is Route 53. Nothing here is a proprietary dead end.

### Slide 6 — Architecture

`2:43 – 3:22`  ·  *39s · 87 words*

> **Delivery:** Follow the two orange arrows down the diagram as you speak.

So how is it built? Lightsail is not a new infrastructure platform. It is a curated control plane over services Amazon already sells. The control plane holds the bundles, the blueprints and the opinionated defaults. Underneath, every resource you create is an ordinary AWS primitive with most of its configuration surface hidden — an instance is EC2, a load balancer is Elastic Load Balancing with a free certificate, a distribution is CloudFront. That hiding is the product. You are trading knobs for a price you can predict.

### Slide 7 — Resource catalogue

`3:22 – 3:48`  ·  *26s · 59 words*

> **Delivery:** Do not read the table. Name three rows and move on.

Ten resource types cover the entire service. I will not read the table, but notice the shape of it: instances and containers for compute; managed databases, block storage and buckets for state; load balancers, distributions, DNS zones and static addresses for delivery. The right-hand column is the honest one — every single row is an existing AWS service, simplified.

### Slide 8 — Blueprints and bundles

`3:48 – 4:28`  ·  *40s · 89 words*

> **Delivery:** The orange box is the most current fact in the deck. Slow down for it.

Creating a server is therefore only two decisions. The blueprint is the software — a plain operating system, or a ready-built stack such as WordPress, LAMP, Node.js or Magento, already installed. The bundle is the hardware and the price, fixed together. One point of currency, in the orange box: Amazon is retiring the Bitnami-packaged blueprints. WordPress, LAMP, Nginx and Node.js images from Bitnami retire this November; the remainder follow in May 2027. AWS-maintained replacements began shipping in January. If you are starting a project today, choose the AWS-maintained image.

### Slide 9 — Instance pricing

`4:28 – 5:08`  ·  *40s · 89 words*

> **Delivery:** Read only the first and last rows aloud. Then the three notes underneath.

Here is the published price list for Linux general-purpose bundles. Five dollars a month buys half a gigabyte of memory, two virtual CPUs, twenty gigabytes of solid-state storage and a terabyte of outbound transfer. At the top, three hundred and eighty-four dollars buys sixty-four gigabytes and eight terabytes of transfer. Three things worth noting underneath. A public IPv4 address is now the premium — go IPv6-only and the entry tier falls to three dollars fifty. Transfer beyond the allowance is metered. And selected entry bundles carry three months free.

### Slide 10 — The rest of the price list

`5:08 – 5:31`  ·  *23s · 52 words*

> **Delivery:** Point at the navy bar and deliver that line as the takeaway.

Everything else follows the same pattern. Containers from seven dollars a node. A managed database from fifteen. A load balancer at eighteen, certificate included. Object storage from one dollar, free for a year. The line at the bottom is the one to remember: Amazon is selling you an allowance, not a meter.

### Slide 11 — Cost comparison

`5:31 – 6:18`  ·  *47s · 106 words*

> **Delivery:** Give the audience three seconds to read the chart before you explain it.

This is where that matters. I priced a Lightsail Small bundle — twelve dollars, three terabytes of transfer included — against the same thing built on EC2 at list price. At a hundred gigabytes of traffic, EC2 costs about twenty-four dollars. At three terabytes — the allowance you already paid for — two hundred and ninety-one dollars. But let me be honest about that chart. Compute is not what drives the gap; data transfer is. At low traffic the two are close, and EC2 wins ground back through Savings Plans. Lightsail's real advantage is bandwidth included in the price, and a number you knew in advance.

### Slide 12 — Networking and security

`6:18 – 6:55`  ·  *37s · 82 words*

> **Delivery:** End on the red line at the bottom. Pause after it.

Every instance carries its own default-deny firewall. A load balancer issues and renews TLS certificates free of charge. A static IPv4 address costs nothing while attached. And resources sit in a Lightsail-managed private cloud that peers with your main one in a single click. But note the line at the bottom, because it is the most commonly misunderstood point about this service: a simpler console does not shrink your security responsibility. Patching the operating system inside that blueprint is still your job.

### Slide 13 — Lightsail versus EC2

`6:55 – 7:32`  ·  *37s · 83 words*

> **Delivery:** Four rows only: pricing, scaling, discounts, best fit.

Four rows tell the story. Pricing: a fixed bundle against per-second metering. Scaling: Lightsail has no auto scaling for instances at all — capacity is a manual decision. Discounts: Lightsail has no Reserved Instances, no Savings Plans, no Spot. The list price is the price. And best fit: predictable small workloads against elastic or compliance-heavy architectures. But these two are not rivals. Lightsail is the on-ramp; EC2 is the motorway. The snapshot export exists precisely so that the journey between them is cheap.

### Slide 14 — The wider market

`7:32 – 8:07`  ·  *35s · 78 words*

> **Delivery:** Concede the price point honestly — it strengthens the next sentence.

Against the wider market, on raw price per gigabyte of memory, Lightsail is competitive rather than cheapest. DigitalOcean starts lower; Linode gives more memory for the same five dollars. Lightsail wins on two things a price list does not show. First, the included transfer allowance — which is exactly where independent VPS bills tend to break. Second, the resource underneath is ordinary AWS, so outgrowing Lightsail is a migration inside one account rather than a change of vendor.

### Slide 15 — Deployment walkthrough

`8:07 – 8:44`  ·  *37s · 82 words*

> **Delivery:** Count the six steps on your fingers. Land firmly on 'ten minutes'.

In practice it looks like this. Pick the WordPress blueprint. Pick a bundle. Create the instance — it boots into a running site in about a minute. Attach a static address. Point a DNS record at it. Enable HTTPS. That is a live, secured, production WordPress site in under ten minutes. The same result on raw EC2 needs all eight of those resources built and wired together first. And none of this is console-only — every step is a single command-line call.

### Slide 16 — Use cases

`8:44 – 9:13`  ·  *29s · 65 words*

> **Delivery:** Two examples aloud, then the closing line.

Websites and blogs, where the bandwidth allowance comfortably covers ordinary traffic. Development and test environments that are created for a sprint and deleted afterwards. Small business applications for teams with no operations staff. Storefronts, coursework, and research computing through Lightsail for Research. The common thread is a workload whose ceiling is known in advance. Lightsail is a poor fit the moment demand becomes genuinely unpredictable.

### Slide 17 — Limitations

`9:13 – 9:48`  ·  *35s · 78 words*

> **Delivery:** Deliver the navy bar as a considered judgement, not an apology.

Which brings me to the limitations. There is no auto scaling. There are no discount instruments. Access control is coarse, so Lightsail is unsuitable wherever least-privilege access is formally audited. Entry bundles run on burstable CPU, which throttles under sustained load. Now — none of these is a defect. Every one of them is the deliberate cost of a fixed price. What matters is that each is also a signal that your workload may have outgrown the service.

### Slide 18 — Growth path

`9:48 – 10:23`  ·  *35s · 79 words*

> **Delivery:** This is the strategic argument. Deliver it as the strongest claim in the talk.

Stay while traffic is predictable, the estate is small, and cost certainty matters more than tuning. Move to EC2 when you need auto scaling, more than sixty-four gigabytes on one machine, proper identity management, or Savings Plans economics. And the exit is built in. Take a snapshot, export it to EC2, and Amazon creates a machine image and a volume snapshot for you to launch. Your disk image is standard AWS — migration is a copy, not a rewrite.

### Slide 19 — Conclusion

`10:23 – 11:10`  ·  *47s · 106 words*

> **Delivery:** Slow down. One beat between each of the four points.

To conclude, four things worth remembering. First, Lightsail sells predictability, not power — the bundle is a price you know before you deploy. Second, it is PaaS-Lite, not PaaS: Amazon pre-builds the operating system and runtime, then still gives you root. Third, the saving is in the bandwidth, not the compute. And fourth, its limitations are its exit signs — when they start to hurt, snapshot and export to EC2. Lightsail is best understood not as a cheaper AWS, but as a narrower one, deliberately designed so that outgrowing it is the expected outcome rather than a failure. Thank you. I am happy to take questions.

### Slide 20 — References

`11:10 – 11:22`  ·  *12s · 27 words*

> **Delivery:** Hold this slide during questions.

My sources are listed here — principally the AWS Lightsail pricing pages, the user guide, and the service announcements from 2026. I will leave this slide up.

---

## Anticipated questions

**Q1. Is Lightsail just a rebranded EC2 instance?**

The compute underneath is EC2, yes — but the product is the packaging: a fixed bundle, a data-transfer allowance, a blueprint that boots ready to serve, and a console with most of the configuration removed. You are buying a pricing model and a set of defaults, not new hardware.

**Q2. Why is it cheaper if it runs on the same hardware?**

For compute alone it largely is not — a t3.small is close to the equivalent bundle. The difference is data transfer. EC2 bills egress per gigabyte after the first 100 GB; Lightsail includes terabytes in the bundle price. AWS is betting most small workloads never use their allowance.

**Q3. Can I use IAM roles and other AWS services with it?**

Partly. Lightsail permissions are coarse compared with full IAM, which rules it out where least-privilege access is audited. You reach the rest of your account through VPC peering — one click connects the Lightsail VPC to your default VPC, after which S3, RDS, Lambda and the rest are reachable.

**Q4. What happens if I exceed the data-transfer allowance?**

You are billed per gigabyte for the overage; the instance is not throttled or stopped. Inbound traffic and traffic to other AWS services in the same Region do not count against the allowance.

**Q5. Is there vendor lock-in?**

Less than with an independent VPS, which is the strategic argument for it. Snapshot export produces a standard AMI and EBS snapshot in EC2, so moving up is a supported workflow inside the same account rather than a rebuild elsewhere.

**Q6. Should I start a new project on a Bitnami blueprint today?**

No. AWS stopped shipping newer Bitnami-packaged images in May 2026, and the WordPress, LAMP, Nginx and Node.js ones retire in November 2026. Choose an AWS-maintained blueprint, or a plain OS image and install the stack yourself.
