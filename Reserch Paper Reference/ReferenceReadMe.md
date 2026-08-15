# 🌿 Eco-Route & Carbon Footprint Navigation System

A lightweight, high-efficiency route optimization system that calculates the **greenest path** to minimize $\text{CO}_2$ emissions using classic Data Structures and Algorithms (DSA).

This project directly aligns with **UN Sustainable Development Goal 11 (Sustainable Cities and Communities)** and **Goal 13 (Climate Action)**.

---

## 📌 Table of Contents
1. [Overview](#-overview)
2. [Data Structures & Algorithms Used](#-data-structures--algorithms-used)
3. [Academic Research & References](#-academic-research--references)
4. [How to Reference in Presentation/Report](#-how-to-reference-in-presentationreport)
5. [Installation & Execution](#-installation--execution)

---

## 📖 Overview

Standard navigation software focuses purely on finding the **shortest distance** or **fastest time**. This application introduces **Eco-Routing**: modifying edge weights within a graph to account for carbon emissions based on distance, traffic congestion factor, and mode of transit.

### Carbon Emission Weight Formula
$$\text{Edge Weight (Emission Cost)} = \text{Distance (km)} \times \text{Traffic Factor} \times \text{Transit Emission Rate (g CO}_2\text{/km)}$$

---

## 💡 Data Structures & Algorithms Used

* **Graph (Adjacency List / Matrix):** Represents the city road network where **Vertices (Nodes)** are intersections/locations and **Edges** are road connections.
* **Dijkstra's Algorithm:** Finds the single-source shortest path adapted for non-negative emission cost weights.
* **Priority Queue (Min-Heap):** Optimizes vertex selection during Dijkstra's algorithm, maintaining $O((V + E) \log V)$ time complexity.
* **Hash Map / Table:** Provides $O(1)$ lookup for node location names, transit modes, and emission coefficient factors.

---

## 🔬 Academic Research & References

This project is grounded in published open-access research covering eco-routing models, graph-based transit optimization, and greenhouse gas estimation frameworks.

### Primary References

1. **Yao, Y., & Song, R. (2013).**  
   *Study on Eco-Route Planning Algorithm and Environmental Impact Assessment.*  
   * **Focus:** Demonstrates how substituting travel time with fuel/emission cost factors in Dijkstra-based routing algorithms leads to measurable emission reductions.  
   * **Reference Link:** [ResearchGate PDF Download](https://www.researchgate.net/publication/262959257_Study_on_Eco-Route_Planning_Algorithm_and_Environmental_Impact_Assessment)  
   * **Usage in Project:** Serves as the primary algorithmic justification for using a modified weighted Dijkstra approach for green routing.

2. **Route Optimization in Urban Networks (2020).**  
   *Route Optimization by using Dijkstra's Algorithm for the Waste Management System.* ACM Conference Series.  
   * **Focus:** Demonstrates practical implementation of Dijkstra's algorithm on real-world transportation graphs to minimize transit overhead and environmental footprint.  
   * **Reference Link:** [ResearchGate PDF Download](https://www.researchgate.net/publication/340930047_Route_Optimization_by_using_Dijkstra's_Algorithm_for_the_Waste_Management_System)  
   * **Usage in Project:** Validates graph modeling techniques (nodes as locations, weighted edges as environmental impact vectors).

3. **Lannelongue, L., Grealey, J., & Inouye, M. (2020).**  
   *Green Algorithms: Quantifying the Carbon Footprint of Computation.* arXiv:2007.07610.  
   * **Focus:** Establishes standardized mathematical frameworks for quantifying carbon footprints and $\text{CO}_2$ equivalent ($\text{g CO}_2\text{e}$) parameters.  
   * **Reference Link:** [arXiv PDF Download](https://arxiv.org/abs/2007.07610)  
   * **Usage in Project:** Supplies the baseline emission multiplier constants for different transit modes.

---

## 🎯 How to Reference in Presentation / Report

When presenting this project to evaluators or judges, use the following citations to explain your design choices:

### 1. Algorithmic Foundation (Dijkstra Adaptation)
> *"Our core pathfinding algorithm modifies standard Dijkstra distance logic by incorporating environmental cost vectors. This strategy is adapted directly from the eco-routing models proposed by **Yao & Song (2013)**."*

### 2. Graph Representation & Edge Weighting
> *"Road network segments are represented as adjacency lists where edge weights represent estimated carbon output ($g CO_2$). This approach builds on urban routing methodologies demonstrated in recent ACM transportation studies."*

### 3. Quantitative Carbon Calculation
> *"The emission coefficient constants used for modal comparison (car vs. EV vs. bike) follow standardized GHG assessment principles as outlined in **Lannelongue et al. (2020)**."*

---

## 🛠️ Installation & Execution

### Prerequisites
* Standard C++ / C Compiler (`g++` / `gcc`) or Java Development Kit (JDK).

### Running the Project (C++ Example)
```bash
# Compile the application
g++ -O2 main.cpp -o eco_route

# Run the executable
./eco_route
```

---

## 📜 License
This project is open-source and available under the [MIT License](LICENSE).