# skills/debug_skill.py

def get_long_text(app, **kwargs):
    long_text = """The Impact of Artificial Intelligence on Modern Society

Artificial Intelligence (AI) is no longer a futuristic concept relegated to science fiction novels and Hollywood blockbusters; it is a living, evolving force reshaping the very fabric of human society. From personalized recommendations on streaming platforms to autonomous vehicles, AI has found its way into numerous facets of daily life. This essay explores the multifaceted impact of AI on modern society — the good, the bad, and the complex.

At its core, AI refers to the simulation of human intelligence in machines. These systems are capable of learning from data, recognizing patterns, and making decisions — often faster and more accurately than humans. While AI has existed in some form since the mid-20th century, only in recent years have advances in computing power, big data, and neural networks pushed it into mainstream applications.

One of the most transformative sectors influenced by AI is healthcare. AI-powered diagnostics can detect diseases like cancer, diabetes, and neurological disorders more accurately and earlier than traditional methods. Machine learning models trained on massive datasets can identify subtle anomalies in medical imaging that even seasoned radiologists might miss. Moreover, virtual health assistants and chatbots are improving patient engagement and reducing the workload of healthcare providers. In surgical rooms, AI-assisted robotic systems enhance precision and reduce recovery times. Yet, these benefits do not come without ethical concerns. Who is to blame if an AI misdiagnoses a patient? Should machines be allowed to override human doctors?

Another domain experiencing seismic shifts due to AI is education. Intelligent tutoring systems adapt learning materials to suit individual students’ needs. Language translation tools, automated grading systems, and AI-driven content generation are revolutionizing how knowledge is delivered. Importantly, AI has the potential to democratize education — making high-quality resources accessible to students in remote or underprivileged regions. However, an over-reliance on machines might diminish the value of human interaction and critical thinking. After all, education is not just about information delivery — it’s also about empathy, ethics, and human values.

The workplace is another arena undergoing radical transformation. AI is automating repetitive tasks in industries ranging from manufacturing to customer service. This shift can free humans to focus on more strategic and creative roles. But here’s the caveat: job displacement is a real concern. While new roles such as AI ethicists, data scientists, and prompt engineers are emerging, many traditional roles are becoming obsolete. The fear of “technological unemployment” is not unfounded, particularly in regions where reskilling infrastructure is lacking. Governments and institutions must therefore prioritize lifelong learning and digital literacy to ensure an equitable transition.

Let’s talk about AI in everyday life. Voice assistants like Siri, Alexa, and Google Assistant have become household staples. Recommendation engines curate our music playlists, shopping carts, and even dating matches. AI filters spam, flags harmful content, and powers facial recognition for security. Smart home devices optimize energy usage, enhance convenience, and improve safety. The benefits are immense — but so are the risks. Concerns over privacy, surveillance, and algorithmic bias persist. How much personal data are we willing to trade for convenience? Who controls the data, and how is it used?

AI has also played a pivotal role in scientific discovery and environmental sustainability. Researchers use AI models to simulate climate change, optimize energy systems, and even design new materials and medicines. In agriculture, AI helps monitor crop health, predict yields, and reduce pesticide usage. These innovations are crucial in addressing global challenges like climate change and food insecurity. Yet, the environmental footprint of AI itself — particularly large models that require immense computational power — cannot be ignored. Training a single AI model can generate as much carbon dioxide as five cars over their lifetime.

The creative industries are not immune to AI’s influence either. Tools like ChatGPT, Midjourney, and DALL·E are enabling new forms of expression, allowing anyone to generate text, art, music, or code with minimal technical skills. While this democratization of creativity is exciting, it raises profound questions: What is the nature of authorship when a machine co-creates with a human? Should AI-generated art be eligible for awards? How do we define originality in an age of generative algorithms?

Ethical considerations surrounding AI cannot be overstated. Bias in training data can lead to discriminatory outcomes, particularly in areas like law enforcement, hiring, and credit scoring. Transparency and explainability are crucial — stakeholders must understand how and why an AI system makes a particular decision. Furthermore, the potential misuse of AI in surveillance, autonomous weapons, or deepfakes presents serious threats to democracy and human rights. Regulatory frameworks are urgently needed, yet they must strike a delicate balance: too rigid, and they stifle innovation; too lax, and they risk public harm.

On a more philosophical level, AI challenges our understanding of intelligence, consciousness, and even what it means to be human. If a machine can compose a symphony, write a novel, or diagnose an illness better than a person, where does that leave us? Are we merely biological algorithms, or is there something uniquely human that machines can never replicate — like emotion, intuition, or morality?

It is also important to address the digital divide. While AI offers enormous promise, its benefits are not evenly distributed. Wealthier nations and tech companies dominate the development and deployment of AI systems, potentially exacerbating existing inequalities. Marginalized communities may find themselves on the wrong end of opaque algorithms — over-policed, under-served, and unheard. To create a more just AI future, inclusivity must be at the heart of both policy and design.

Despite these challenges, the potential of AI to uplift humanity remains vast. Used responsibly, AI can enhance quality of life, advance human knowledge, and solve problems once thought intractable. But this requires collaboration across disciplines — ethicists, engineers, policymakers, educators, and the public must all have a seat at the table. The goal is not to resist AI, but to shape it — to ensure that it reflects our values and serves the common good.

In conclusion, Artificial Intelligence is neither a silver bullet nor a ticking time bomb. It is a tool — powerful, evolving, and ultimately neutral. Its impact on society depends not just on what it can do, but on what we choose to do with it. The future of AI is, quite literally, in our hands."""
    return long_text

def register():
    """Registers debug commands using the new standard format."""
    return {
        'get_long_text': {
            'handler': get_long_text,
            'regex': r'/long text',
            'params': []
        }
    }